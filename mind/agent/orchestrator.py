"""
Orquestador del agente LLM de Mind by Versat.
Implementa el loop de tool-calling con OpenAI/OpenRouter.
Multi-tenant: carga AgentConfig filtrado por tenant_id.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from openai import AsyncOpenAI, APIError, APITimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from mind.auth.authorization import AuthResult
from mind.db.models import Tenant

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """Eres Mind, un asistente ejecutivo de inteligencia artificial para la empresa.
Tu función es consultar datos reales de la empresa usando las herramientas disponibles.

REGLAS CRÍTICAS — NUNCA las ignores:
- Cuando el usuario pida datos de ventas, finanzas, productos, indicadores o cuentas por pagar: SIEMPRE llama la herramienta correspondiente PRIMERO. NUNCA respondas que no tienes acceso sin intentarlo.
- NUNCA digas "hay un problema técnico" sin haber intentado llamar la herramienta.
- NUNCA inventes datos. Si la herramienta retorna error, muestra el mensaje de error exacto al usuario.
- Responde en español siempre.
- Después de llamar una herramienta, interpreta los resultados y preséntelos de forma clara y ejecutiva.

Herramientas disponibles:
- consultar_ventas: ventas del período (usa año actual si no especifican)
- consultar_ventas_detalle: detalle de transacciones
- consultar_indicadores: KPIs del año actual
- consultar_finanzas: CxP, abonos, cuadre de caja
- consultar_productos: catálogo de productos
- consultar_cxp: cuentas por pagar
- generar_informe: genera PDF o Excel
- crear_tarea_programada / listar_tareas / eliminar_tarea / modificar_tarea"""


@dataclass
class AgentResult:
    """Resultado del procesamiento del agente."""
    text: str
    file_path: str | None = None
    file_caption: str | None = None


async def process(
    message: str,
    chat_id: int,
    tenant: Tenant,
    auth_result: AuthResult,
    session: AsyncSession,
) -> AgentResult:
    """
    Procesa un mensaje del usuario usando el loop LLM con tool-calling.
    El tenant determina: AgentConfig, credenciales SQL Server y permisos.
    """
    from mind.config import settings
    from mind.agent.context import (
        load_history, append_messages, build_prompt,
        truncate_to_token_limit, Message,
    )
    from mind.agent.tools.registry import (
        dispatch, get_tool_schemas,
        PermissionDeniedError, ToolNotFoundError, ToolValidationError,
    )
    from mind.audit.logger import AuditRecord, log_interaction, log_tool_failure
    from mind.tenants.context import set_tenant

    # Establecer tenant en el contexto async (para connectors.py)
    set_tenant(tenant)

    # --- Cargar configuración dinámica del agente desde BD (por tenant) ---
    active_system_prompt = DEFAULT_SYSTEM_PROMPT
    active_model = settings.OPENAI_MODEL
    active_window = settings.CONVERSATION_WINDOW
    active_max_cycles = settings.AGENT_MAX_TOOL_CYCLES
    try:
        from sqlalchemy import select
        from mind.db.models import AgentConfig
        cfg = (await session.execute(
            select(AgentConfig).where(AgentConfig.tenant_id == tenant.id).limit(1)
        )).scalar_one_or_none()
        if cfg:
            active_system_prompt = cfg.system_prompt or DEFAULT_SYSTEM_PROMPT
            active_model = cfg.model or settings.OPENAI_MODEL
            active_window = cfg.conversation_window
            active_max_cycles = cfg.max_tool_cycles
    except Exception:
        pass

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )

    # --- 1. Cargar historial del tenant+chat ---
    try:
        history = await load_history(chat_id, tenant.id, active_window, session)
    except Exception as exc:
        logger.warning(
            "No se pudo cargar historial para tenant=%s chat_id=%s: %s",
            tenant.id, chat_id, type(exc).__name__,
        )
        history = []

    # --- 2. Obtener permisos del usuario ---
    user_permissions: frozenset[str] = frozenset()
    if auth_result.role:
        from sqlalchemy import select
        from mind.db.models import RolePermission
        stmt = select(RolePermission.permission_name).where(
            RolePermission.role_id == auth_result.role.id
        )
        result = await session.execute(stmt)
        user_permissions = frozenset(row[0] for row in result.fetchall())

    # --- 3. Construir messages para OpenAI ---
    prompt_ctx = build_prompt(history, active_window)
    truncated = truncate_to_token_limit(prompt_ctx.messages, max_tokens=100_000)

    openai_messages: list[dict[str, Any]] = [
        {"role": "system", "content": active_system_prompt}
    ]
    openai_messages.extend(m.to_openai_dict() for m in truncated)
    openai_messages.append({"role": "user", "content": message})

    tools = get_tool_schemas()
    logger.info(
        "tenant=%s chat_id=%s permisos=%s tools=%s",
        tenant.slug, chat_id, user_permissions,
        [t["function"]["name"] for t in tools],
    )

    new_messages: list[Message] = [Message(role="user", content=message)]
    file_path: str | None = None
    file_caption: str | None = None
    final_text: str = ""

    # --- 4. Loop de tool-calling ---
    try:
        for cycle in range(active_max_cycles):
            response = await client.chat.completions.create(
                model=active_model,
                messages=openai_messages,
                tools=tools if tools else None,
                tool_choice="auto",
            )

            choice = response.choices[0]

            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                final_text = choice.message.content or ""
                new_messages.append(Message(role="assistant", content=final_text))
                break

            tool_calls = choice.message.tool_calls
            assistant_content = choice.message.content or ""

            openai_messages.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    raw_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    raw_args = {}

                try:
                    tool_result_str = await dispatch(tool_name, raw_args, user_permissions)
                    tool_result_data = json.loads(tool_result_str)

                    if not tool_result_data.get("error") and "file_path" in tool_result_data:
                        file_path = tool_result_data["file_path"]
                        file_caption = (
                            f"📊 {tool_result_data.get('tipo', 'Informe')} — "
                            f"{tool_result_data.get('periodo', '')}"
                        )

                except PermissionDeniedError as exc:
                    tool_result_str = json.dumps({
                        "error": True,
                        "mensaje": "No tienes permiso para ejecutar esta acción.",
                    })
                    await log_tool_failure(
                        tool_name=tool_name,
                        params=raw_args,
                        error=str(exc),
                        chat_id=chat_id,
                        tenant_id=tenant.id,
                    )

                except (ToolNotFoundError, ToolValidationError) as exc:
                    logger.error("Tool error %s: %s", tool_name, exc)
                    tool_result_str = json.dumps({
                        "error": True,
                        "mensaje": f"Error ejecutando {tool_name}: {exc}",
                    })
                    await log_tool_failure(
                        tool_name=tool_name,
                        params=raw_args,
                        error=str(exc),
                        chat_id=chat_id,
                        tenant_id=tenant.id,
                    )

                except Exception as exc:
                    import traceback
                    logger.error(
                        "Error en herramienta %s tenant=%s: %s\n%s",
                        tool_name, tenant.slug, exc, traceback.format_exc(),
                    )
                    tool_result_str = json.dumps({
                        "error": True,
                        "mensaje": "Ocurrió un error al ejecutar la herramienta.",
                    })
                    await log_tool_failure(
                        tool_name=tool_name,
                        params=raw_args,
                        error=str(exc),
                        chat_id=chat_id,
                        tenant_id=tenant.id,
                    )

                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result_str,
                })

        else:
            final_text = (
                "Lo siento, no pude completar tu solicitud en este momento. "
                "Por favor intenta de nuevo con una solicitud más específica."
            )
            new_messages.append(Message(role="assistant", content=final_text))

    except APITimeoutError:
        final_text = "La solicitud tardó demasiado. Por favor intenta de nuevo en unos momentos."
        new_messages.append(Message(role="assistant", content=final_text))

    except APIError as exc:
        logger.error("OpenAI API error tenant=%s chat_id=%s: %s", tenant.slug, chat_id, type(exc).__name__)
        final_text = "Ocurrió un error procesando tu solicitud. Por favor intenta de nuevo."
        new_messages.append(Message(role="assistant", content=final_text))

    except Exception as exc:
        logger.error("Error inesperado tenant=%s chat_id=%s: %s", tenant.slug, chat_id, type(exc).__name__)
        final_text = "Ocurrió un error inesperado. Por favor contacta al administrador."
        new_messages.append(Message(role="assistant", content=final_text))

    # --- 5. Persistir historial ---
    try:
        await append_messages(chat_id, tenant.id, new_messages, session)
        await session.commit()
    except Exception as exc:
        logger.warning(
            "No se pudo persistir historial tenant=%s chat_id=%s: %s",
            tenant.slug, chat_id, type(exc).__name__,
        )

    # --- 6. Registrar en auditoría ---
    user_id = auth_result.user.user_id if auth_result.user else None
    await log_interaction(AuditRecord(
        event_type="interaction",
        chat_id=chat_id,
        user_id=user_id,
        request_content=message,
        response_content=final_text,
        status="success",
        tenant_id=tenant.id,
    ))

    return AgentResult(text=final_text, file_path=file_path, file_caption=file_caption)

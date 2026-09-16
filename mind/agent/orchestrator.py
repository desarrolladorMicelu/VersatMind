"""
Orquestador del agente LLM de Mind by Versat.
Implementa el loop de tool-calling con OpenAI GPT-4o.
Requisitos: 3.1 - 3.9, 4.5, 9.7
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
from mind.db.models import User

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres Mind, un asistente ejecutivo de inteligencia artificial para la empresa.
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
    auth_result: AuthResult,
    session: AsyncSession,
) -> AgentResult:
    """
    Procesa un mensaje del usuario usando el loop LLM con tool-calling.

    Flujo:
    1. Carga historial de conversación.
    2. Construye prompt con system + history + user message.
    3. Loop hasta MAX_TOOL_CYCLES:
       - Llama al LLM con tools disponibles.
       - Si respuesta directa → retorna.
       - Si tool_calls → despacha herramientas y continúa.
    4. Si se agotan ciclos → retorna mensaje de error.
    5. Persiste historial y registra en auditoría.

    Requisitos: 3.1-3.9, 4.5
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

    # --- Cargar configuración dinámica desde BD ---
    active_system_prompt = SYSTEM_PROMPT
    active_model = settings.OPENAI_MODEL
    active_window = settings.CONVERSATION_WINDOW
    active_max_cycles = settings.AGENT_MAX_TOOL_CYCLES
    try:
        from sqlalchemy import select
        from mind.db.models import AgentConfig
        cfg = (await session.execute(select(AgentConfig).limit(1))).scalar_one_or_none()
        if cfg:
            active_system_prompt = cfg.system_prompt or SYSTEM_PROMPT
            active_model = cfg.model or settings.OPENAI_MODEL
            active_window = cfg.conversation_window
            active_max_cycles = cfg.max_tool_cycles
    except Exception:
        pass  # Si falla la BD usa los valores por defecto

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )

    # --- 1. Cargar historial ---
    try:
        history = await load_history(chat_id, active_window, session)
    except Exception as exc:
        logger.warning("No se pudo cargar historial para chat_id=%s: %s", chat_id, type(exc).__name__)
        history = []
        # Notificación al usuario se incluye en el contexto del system

    # Obtener permisos del usuario
    user_permissions: frozenset[str] = frozenset()
    if auth_result.role:
        from sqlalchemy import select
        from mind.db.models import RolePermission
        stmt = select(RolePermission.permission_name).where(
            RolePermission.role_id == auth_result.role.id
        )
        result = await session.execute(stmt)
        user_permissions = frozenset(row[0] for row in result.fetchall())

    # --- 2. Construir messages para OpenAI ---
    prompt_ctx = build_prompt(history, settings.CONVERSATION_WINDOW)
    truncated = truncate_to_token_limit(prompt_ctx.messages, max_tokens=100_000)

    openai_messages: list[dict[str, Any]] = [{"role": "system", "content": active_system_prompt}]
    openai_messages.extend(m.to_openai_dict() for m in truncated)
    openai_messages.append({"role": "user", "content": message})

    tools = get_tool_schemas()
    logger.info("Permisos del usuario chat_id=%s: %s", chat_id, user_permissions)
    logger.info("Herramientas disponibles: %s", [t['function']['name'] for t in tools])
    new_messages: list[Message] = [
        Message(role="user", content=message)
    ]
    file_path: str | None = None
    file_caption: str | None = None
    final_text: str = ""

    # --- 3. Loop de tool-calling ---
    try:
        for cycle in range(active_max_cycles):
            response = await client.chat.completions.create(
                model=active_model,
                messages=openai_messages,
                tools=tools if tools else None,
                tool_choice="auto",
            )

            choice = response.choices[0]

            # Respuesta directa (sin tools)
            if choice.finish_reason == "stop" or not choice.message.tool_calls:
                final_text = choice.message.content or ""
                assistant_msg = Message(role="assistant", content=final_text)
                new_messages.append(assistant_msg)
                break

            # Tool calls
            tool_calls = choice.message.tool_calls
            assistant_content = choice.message.content or ""

            # Agregar mensaje del asistente (puede estar vacío) a la cadena
            openai_messages.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })
            # Despachar cada tool call
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    raw_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    raw_args = {}

                try:
                    tool_result_str = await dispatch(tool_name, raw_args, user_permissions)
                    tool_result_data = json.loads(tool_result_str)

                    # Detectar si el resultado contiene un archivo a enviar
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
                    )

                except Exception as exc:
                    import traceback
                    logger.error("Error en herramienta %s: %s\n%s", tool_name, exc, traceback.format_exc())
                    tool_result_str = json.dumps({
                        "error": True,
                        "mensaje": "Ocurrió un error al ejecutar la herramienta.",
                    })
                    await log_tool_failure(
                        tool_name=tool_name,
                        params=raw_args,
                        error=str(exc),
                        chat_id=chat_id,
                    )

                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result_str,
                })

        else:
            # Se agotaron los ciclos sin respuesta final — Requisito 3.9
            final_text = (
                "Lo siento, no pude completar tu solicitud en este momento. "
                "Por favor intenta de nuevo con una solicitud más específica."
            )
            new_messages.append(Message(role="assistant", content=final_text))

    except APITimeoutError:
        final_text = (
            "La solicitud tardó demasiado. Por favor intenta de nuevo en unos momentos."
        )
        new_messages.append(Message(role="assistant", content=final_text))
        # Registrar en auditoría se hace abajo

    except APIError as exc:
        logger.error("OpenAI API error para chat_id=%s: %s", chat_id, type(exc).__name__)
        final_text = (
            "Ocurrió un error procesando tu solicitud. Por favor intenta de nuevo."
        )
        new_messages.append(Message(role="assistant", content=final_text))

    except Exception as exc:
        logger.error("Error inesperado para chat_id=%s: %s", chat_id, type(exc).__name__)
        final_text = "Ocurrió un error inesperado. Por favor contacta al administrador."
        new_messages.append(Message(role="assistant", content=final_text))

    # --- 4. Persistir historial ---
    try:
        await append_messages(chat_id, new_messages, session)
        await session.commit()
    except Exception as exc:
        logger.warning("No se pudo persistir historial para chat_id=%s: %s", chat_id, type(exc).__name__)

    # --- 5. Registrar en auditoría ---
    user_id = auth_result.user.user_id if auth_result.user else None
    audit_record = AuditRecord(
        event_type="interaction",
        chat_id=chat_id,
        user_id=user_id,
        request_content=message,
        response_content=final_text,
        status="success" if final_text else "error",
    )
    await log_interaction(audit_record)

    return AgentResult(
        text=final_text,
        file_path=file_path,
        file_caption=file_caption,
    )

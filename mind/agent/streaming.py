"""
Versión en streaming del agente para la interfaz web de chat.

Reutiliza la misma lógica del orquestador (config por tenant, MCPs, base de
conocimiento, contexto temporal, permisos y herramientas) pero usa
`stream=True` para emitir el texto token a token y notificar cuándo el agente
invoca una herramienta.

Emite eventos (dicts) que el endpoint SSE serializa:
  {"type": "status", "stage": "thinking"}
  {"type": "tool", "name", "label", "status": "running"|"done", "ok"}
  {"type": "delta", "text"}
  {"type": "done", "text", "usage"}
  {"type": "error", "message"}
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI, APIError, APITimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from mind.db.models import Tenant
from mind.agent.orchestrator import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


TOOL_LABELS: dict[str, str] = {
    "consultar_ventas": "Consultando ventas",
    "consultar_ventas_detalle": "Consultando detalle de ventas",
    "consultar_indicadores": "Consultando indicadores",
    "consultar_finanzas": "Consultando finanzas",
    "consultar_productos": "Consultando productos",
    "consultar_cxp": "Consultando cuentas por pagar",
    "generar_informe": "Generando informe",
    "crear_tarea_programada": "Programando tarea",
    "listar_tareas": "Listando tareas",
    "modificar_tarea": "Modificando tarea",
    "eliminar_tarea": "Eliminando tarea",
    "ejecutar_consulta": "Consultando base de datos",
    "consultar_sheet": "Consultando Google Sheets",
    "consultar_alegra": "Consultando Alegra",
    "generar_informe_contable": "Generando informe contable",
}


def tool_label(name: str) -> str:
    return TOOL_LABELS.get(name, name)


async def _build_system_prompt(
    session: AsyncSession, tenant: Tenant, message: str, base_prompt: str
) -> str:
    """Inyecta MCPs/base de conocimiento/contexto temporal, igual que el orquestador."""
    prompt = base_prompt

    schema_description = (getattr(tenant, "external_db", None) or {}).get("schema_description")
    if schema_description:
        prompt += (
            "\n\n## Base de datos externa del cliente\n\n"
            "Tienes disponible una base de datos externa con este esquema:\n\n"
            f"{schema_description}\n\n"
            "REGLAS PARA USAR 'ejecutar_consulta':\n"
            "1. USA SIEMPRE 'ejecutar_consulta' para responder preguntas sobre datos. "
            "NUNCA uses 'crear_tarea_programada' para consultas inmediatas.\n"
            "2. Siempre haz JOIN entre tablas relacionadas (FK) para mostrar nombres "
            "legibles, NUNCA IDs numéricos.\n"
            "3. Usa SOLO los nombres de columna exactos del esquema.\n"
            "4. Si una consulta falla, intenta una versión más simple antes de rendirte.\n"
            "5. Los valores como status están en INGLÉS y MAYÚSCULAS; usa los exactos.\n"
            "Limita resultados con LIMIT."
        )

    sheets_description = (getattr(tenant, "external_sheets", None) or {}).get("schema_description")
    if sheets_description:
        prompt += (
            "\n\n## Google Sheets del cliente\n\n"
            "Tienes disponible una hoja de cálculo con este contenido:\n\n"
            f"{sheets_description}\n\n"
            "Para consultarla usa 'consultar_sheet' con el nombre exacto de la hoja."
        )

    alegra_description = (getattr(tenant, "external_alegra", None) or {}).get("schema_description")
    if alegra_description:
        prompt += (
            "\n\n" + alegra_description + "\n\n"
            "Para consultarla usa 'consultar_alegra' con una descripción en lenguaje "
            "natural. Sé específico con fechas y nombres."
        )

    report_cfg = getattr(tenant, "report_config", None)
    if report_cfg and report_cfg.get("company_name"):
        sections_list = ", ".join(report_cfg.get("sections", ["balance", "income", "expenses"]))
        instructions = report_cfg.get("additional_instructions", "")
        prompt += (
            "\n\n## Informes contables personalizados\n\n"
            f"Puedes generar informes contables PDF para {report_cfg['company_name']}. "
            f"Secciones habilitadas: {sections_list}.\n"
        )
        if instructions:
            prompt += f"Instrucciones: {instructions}\n"

    try:
        from mind.scheduler.prompts import build_context
        ctx = build_context(tenant)
        prompt += (
            "\n\n## Contexto temporal\n"
            f"Hoy es {ctx['fecha_larga']} ({ctx['fecha']}). "
            f"Ayer fue {ctx['ayer']}. Inicio de la semana: {ctx['inicio_semana']}. "
            f"Inicio del mes: {ctx['inicio_mes']}. "
            "Interpreta expresiones relativas ('hoy', 'ayer', 'esta semana', "
            "'este mes') usando estas fechas."
        )
    except Exception:
        pass

    try:
        from mind.knowledge.retriever import build_knowledge_context
        knowledge = await build_knowledge_context(session, tenant.id, message)
        if knowledge:
            prompt += (
                "\n\n## Base de conocimiento del cliente\n\n"
                f"{knowledge}\n\n"
                "Usa esta información cuando sea relevante. No la contradigas."
            )
    except Exception:
        pass

    return prompt


def _filter_tools(tools: list[dict], tenant: Tenant) -> list[dict]:
    tenant_ofima = bool(tenant.sqlserver_host)
    tenant_ext_db = bool(tenant.external_db)
    tenant_ext_sheets = bool(tenant.external_sheets)
    tenant_alegra = bool(tenant.external_alegra and tenant.external_alegra.get("token"))
    ofima_tools = {
        "consultar_ventas", "consultar_ventas_detalle", "consultar_indicadores",
        "consultar_finanzas", "consultar_productos", "consultar_cxp", "generar_informe",
    }
    task_tools = {"crear_tarea_programada", "listar_tareas", "eliminar_tarea", "modificar_tarea"}
    result = []
    for t in tools:
        name = t["function"]["name"]
        if name in ofima_tools and not tenant_ofima:
            continue
        if name in task_tools and not tenant_ofima:
            continue
        if name == "ejecutar_consulta" and not tenant_ext_db:
            continue
        if name == "consultar_sheet" and not tenant_ext_sheets:
            continue
        if name == "consultar_alegra" and not tenant_alegra:
            continue
        result.append(t)
    return result


async def stream_chat(
    *,
    message: str,
    chat_id: int,
    tenant: Tenant,
    session: AsyncSession,
    owner: str | None = None,
    source: str = "web_chat",
    forced_permissions: frozenset[str] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Genera eventos del agente en streaming para una conversación."""
    from mind.config import settings
    from mind.agent.context import (
        load_history, append_messages, build_prompt, truncate_to_token_limit, Message,
    )
    from mind.agent.tools.registry import (
        dispatch, get_tool_schemas,
        PermissionDeniedError, ToolNotFoundError, ToolValidationError,
    )
    from mind.audit.logger import AuditRecord, log_interaction, log_tool_failure
    from mind.tenants.context import set_tenant
    from mind.usage.tracker import record_usage

    set_tenant(tenant)

    # Configuración dinámica del agente por tenant
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

    active_system_prompt = await _build_system_prompt(session, tenant, message, active_system_prompt)

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )

    history = await load_history(chat_id, tenant.id, active_window, session)
    permissions = forced_permissions if forced_permissions is not None else frozenset()

    prompt_ctx = build_prompt(history, active_window)
    truncated = truncate_to_token_limit(prompt_ctx.messages, max_tokens=100_000)
    openai_messages: list[dict[str, Any]] = [
        {"role": "system", "content": active_system_prompt}
    ]
    openai_messages.extend(m.to_openai_dict() for m in truncated)
    openai_messages.append({"role": "user", "content": message})

    tools = _filter_tools(get_tool_schemas(), tenant)

    new_messages: list[Message] = [Message(role="user", content=message)]
    final_text = ""
    usage_prompt = 0
    usage_completion = 0

    yield {"type": "status", "stage": "thinking"}

    try:
        for cycle in range(active_max_cycles):
            first_tool_choice = (
                {"type": "function", "function": {"name": tools[0]["function"]["name"]}}
                if cycle == 0 and tools and len(tools) == 1
                else "auto"
            )

            content_parts: list[str] = []
            tool_calls_acc: dict[int, dict[str, str]] = {}

            try:
                stream = await client.chat.completions.create(
                    model=active_model,
                    messages=openai_messages,
                    tools=tools if tools else None,
                    tool_choice=first_tool_choice,
                    stream=True,
                    stream_options={"include_usage": True},
                )
            except (APIError, TypeError):
                # Algunos proveedores no soportan stream_options: reintentar sin él.
                stream = await client.chat.completions.create(
                    model=active_model,
                    messages=openai_messages,
                    tools=tools if tools else None,
                    tool_choice=first_tool_choice,
                    stream=True,
                )

            async for chunk in stream:
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage_prompt += int(getattr(chunk_usage, "prompt_tokens", 0) or 0)
                    usage_completion += int(getattr(chunk_usage, "completion_tokens", 0) or 0)

                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                delta = choices[0].delta
                if delta is None:
                    continue

                content = getattr(delta, "content", None)
                if content:
                    content_parts.append(content)
                    yield {"type": "delta", "text": content}

                delta_tool_calls = getattr(delta, "tool_calls", None)
                if delta_tool_calls:
                    for tc in delta_tool_calls:
                        idx = getattr(tc, "index", 0) or 0
                        acc = tool_calls_acc.setdefault(
                            idx, {"id": "", "name": "", "arguments": ""}
                        )
                        if getattr(tc, "id", None):
                            acc["id"] = tc.id
                        fn = getattr(tc, "function", None)
                        if fn is not None:
                            if getattr(fn, "name", None):
                                acc["name"] = fn.name
                            if getattr(fn, "arguments", None):
                                acc["arguments"] += fn.arguments

            assistant_content = "".join(content_parts)

            if not tool_calls_acc:
                final_text = assistant_content
                new_messages.append(Message(role="assistant", content=final_text))
                break

            openai_messages.append({
                "role": "assistant",
                "content": assistant_content or None,
                "tool_calls": [
                    {
                        "id": a["id"],
                        "type": "function",
                        "function": {"name": a["name"], "arguments": a["arguments"]},
                    }
                    for a in tool_calls_acc.values()
                ],
            })

            for a in tool_calls_acc.values():
                tool_name = a["name"]
                try:
                    raw_args = json.loads(a["arguments"] or "{}")
                except json.JSONDecodeError:
                    raw_args = {}

                yield {
                    "type": "tool",
                    "name": tool_name,
                    "label": tool_label(tool_name),
                    "status": "running",
                    "args": raw_args,
                }

                ok = True
                try:
                    tool_result_str = await dispatch(tool_name, raw_args, permissions)
                except PermissionDeniedError as exc:
                    ok = False
                    tool_result_str = json.dumps({
                        "error": True, "mensaje": "No tienes permiso para ejecutar esta acción.",
                    })
                    await log_tool_failure(
                        tool_name=tool_name, params=raw_args, error=str(exc),
                        chat_id=chat_id, tenant_id=tenant.id,
                    )
                except (ToolNotFoundError, ToolValidationError) as exc:
                    ok = False
                    tool_result_str = json.dumps({
                        "error": True, "mensaje": f"Error ejecutando {tool_name}: {exc}",
                    })
                    await log_tool_failure(
                        tool_name=tool_name, params=raw_args, error=str(exc),
                        chat_id=chat_id, tenant_id=tenant.id,
                    )
                except Exception as exc:
                    ok = False
                    logger.error("Error en herramienta %s tenant=%s: %s", tool_name, tenant.slug, exc)
                    tool_result_str = json.dumps({
                        "error": True, "mensaje": "Ocurrió un error al ejecutar la herramienta.",
                    })
                    await log_tool_failure(
                        tool_name=tool_name, params=raw_args, error=str(exc),
                        chat_id=chat_id, tenant_id=tenant.id,
                    )

                yield {
                    "type": "tool",
                    "name": tool_name,
                    "label": tool_label(tool_name),
                    "status": "done",
                    "ok": ok,
                }
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": a["id"],
                    "content": tool_result_str,
                })
        else:
            final_text = (
                "Lo siento, no pude completar tu solicitud en este momento. "
                "Por favor intenta de nuevo con una solicitud más específica."
            )
            new_messages.append(Message(role="assistant", content=final_text))
            yield {"type": "delta", "text": final_text}

    except APITimeoutError:
        final_text = "La solicitud tardó demasiado. Por favor intenta de nuevo en unos momentos."
        new_messages.append(Message(role="assistant", content=final_text))
        yield {"type": "error", "message": final_text}
    except APIError as exc:
        logger.error("OpenAI API error tenant=%s chat_id=%s: %s", tenant.slug, chat_id, type(exc).__name__)
        final_text = "Ocurrió un error procesando tu solicitud. Por favor intenta de nuevo."
        new_messages.append(Message(role="assistant", content=final_text))
        yield {"type": "error", "message": final_text}
    except Exception as exc:
        logger.error("Error inesperado tenant=%s chat_id=%s: %s", tenant.slug, chat_id, type(exc).__name__)
        final_text = "Ocurrió un error inesperado. Por favor contacta al administrador."
        new_messages.append(Message(role="assistant", content=final_text))
        yield {"type": "error", "message": final_text}

    # Persistir historial
    try:
        await append_messages(chat_id, tenant.id, new_messages, session)
        await session.commit()
    except Exception as exc:
        logger.warning(
            "No se pudo persistir historial tenant=%s chat_id=%s: %s",
            tenant.slug, chat_id, type(exc).__name__,
        )

    # Auditoría
    try:
        await log_interaction(AuditRecord(
            event_type="interaction",
            chat_id=chat_id,
            user_id=None,
            request_content=message,
            response_content=final_text,
            status="success",
            tenant_id=tenant.id,
        ))
    except Exception:
        pass

    # Consumo de tokens
    await record_usage(
        tenant_id=tenant.id,
        chat_id=chat_id,
        user_id=None,
        username=owner,
        model=active_model,
        prompt_tokens=usage_prompt,
        completion_tokens=usage_completion,
        source=source,
    )

    yield {
        "type": "done",
        "text": final_text,
        "usage": {"prompt_tokens": usage_prompt, "completion_tokens": usage_completion},
    }

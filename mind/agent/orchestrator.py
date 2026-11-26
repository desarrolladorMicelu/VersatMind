"""
Orquestador del agente LLM de Mind by Versat.
Implementa el loop de tool-calling con OpenAI/OpenRouter.
Multi-tenant: carga AgentConfig filtrado por tenant_id.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI, APIError, APITimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from mind.auth.authorization import AuthResult
from mind.auth.data_policy import (
    SourcePolicy,
    empty_policy,
    load_permissions_for_roles,
    load_source_policy,
    load_user_role_ids,
)
from mind.db.models import Tenant
from mind.usage.tracker import record_usage

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """Eres Mind, un asistente ejecutivo de inteligencia artificial para la empresa.
Tu función es consultar datos reales de la empresa usando las herramientas disponibles.

REGLAS CRÍTICAS — NUNCA las ignores:
- Cuando el usuario pida datos de ventas, finanzas, productos, indicadores o cuentas por pagar: SIEMPRE llama la herramienta correspondiente PRIMERO. NUNCA respondas que no tienes acceso sin intentarlo cuando la herramienta este habilitada. Si la herramienta o fuente NO esta en la lista habilitada, no inventes ni supongas datos: indica que no tienes acceso y pide autorizacion al administrador; no reveles nombres de tablas, archivos o fuentes no autorizadas.
- Cuando el usuario pregunte por datos de la base de datos externa (ventas, usuarios, productos, órdenes, clientes, etc.): DEBES llamar 'ejecutar_consulta'. Es OBLIGATORIO. NUNCA respondas sin haber llamado la herramienta primero — aunque creas saber la respuesta.
- Si no llamas una herramienta cuando el usuario pregunta por datos, tu respuesta será INCORRECTA.
- NUNCA digas "hay un problema técnico" sin haber intentado llamar la herramienta.
- NUNCA inventes datos. Si la herramienta retorna error, muestra el mensaje de error exacto al usuario.
- Si una consulta SQL falla, intenta una versión más simple (menos JOINs, menos condiciones) antes de rendirte.
- Responde en español siempre.
- Después de llamar una herramienta, interpreta los resultados y preséntelos de forma clara y ejecutiva.

Usa únicamente las herramientas que se te entregan en esta conversación.
La lista exacta de herramientas habilitadas para este usuario aparece al final del prompt.

Cuando pregunten por precios, stock, IMEI, gangazos, historial de un cliente, proveedores,
arqueos o sincronización, USA la herramienta correspondiente (no inventes datos).

Cuando uses rangos de fechas: 'fecha_fin' es el ÚLTIMO DÍA INCLUIDO. Si el usuario pide
"agosto", usa fecha_inicio=2026-08-01 y fecha_fin=2026-08-31 (incluye el 31)."""


@dataclass
class AgentResult:
    """Resultado del procesamiento del agente."""
    text: str
    file_path: str | None = None
    file_caption: str | None = None


def tool_catalog(tools: list[dict]) -> str:
    """Catálogo de herramientas permitidas para inyectar en el prompt."""
    lines = ["Herramientas habilitadas para este usuario:"]
    for tool in tools:
        fn = tool.get("function", {})
        name = fn.get("name")
        if name:
            lines.append(f"- {name}: {fn.get('description', '')}")
    return "\n".join(lines)


async def process(
    message: str,
    chat_id: int,
    tenant: Tenant,
    auth_result: AuthResult,
    session: AsyncSession,
    source: str = "chat",
    forced_permissions: frozenset[str] | None = None,
    persist_history: bool = True,
    source_policy: SourcePolicy | None = None,
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
        dispatch, get_allowed_tool_schemas,
        PermissionDeniedError, ToolNotFoundError, ToolValidationError,
    )
    from mind.audit.logger import (
        AuditRecord, log_interaction, log_permission_denied, log_tool_failure,
    )
    from mind.auth.context import set_current_permissions
    from mind.reports.context import set_report_context
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

    set_report_context(
        tenant_id=tenant.id,
        owner=None,
        conversation_id=None,
        chat_id=chat_id,
        channel="web" if source == "web_chat" else "telegram",
    )

    # --- Permisos funcionales + política de fuentes ---
    role_ids: frozenset[int] = frozenset()
    if forced_permissions is not None:
        user_permissions = forced_permissions
        policy = source_policy or empty_policy()
    elif auth_result.user is not None or auth_result.role is not None:
        if auth_result.user is not None:
            role_ids = await load_user_role_ids(session, auth_result.user)
        elif auth_result.role is not None:
            role_ids = frozenset({auth_result.role.id})
        user_permissions = await load_permissions_for_roles(session, role_ids)
        policy = await load_source_policy(session, role_ids, tenant.id)
    else:
        user_permissions = frozenset()
        policy = empty_policy()
    set_current_permissions(user_permissions)

    # Inyectar el esquema de la base de datos externa del cliente si existe
    ext_db = getattr(tenant, "external_db", None)
    schema_description = (ext_db or {}).get("schema_description")
    if schema_description and policy.allows("external_db"):
        active_system_prompt += (
            "\n\n## Base de datos externa del cliente\n\n"
            "Tienes disponible una base de datos externa con este esquema:\n\n"
            f"{schema_description}\n\n"
            "REGLAS PARA USAR 'ejecutar_consulta':\n"
            "1. USA SIEMPRE 'ejecutar_consulta' para responder preguntas sobre datos. "
            "NUNCA uses 'crear_tarea_programada' para consultas inmediatas.\n"
            "2. Siempre haz JOIN entre tablas relacionadas (FK) para mostrar nombres "
            "legibles, NUNCA IDs numéricos.\n"
            "3. Usa SOLO los nombres de columna exactos del esquema. "
            "No los traduzcas al español ni uses alias con comillas dobles.\n"
            "4. Si un nombre de tabla o columna tiene MAYÚSCULAS o caracteres "
            "especiales (ej: Usuarios, Tickets, Puntos_Clientes), escríbelo "
            "SIEMPRE entre comillas dobles en el SQL: \"Usuarios\". Sin comillas "
            "PostgreSQL lo convierte a minúsculas y falla con 'relation ... does not exist'.\n"
            "5. Si una columna es de tipo texto (character varying) pero su nombre y "
            "valores sugieren que contiene números (ej: un campo llamado total, "
            "cantidad, precio, monto, impuesto), conviértela ANTES de usarla con "
            "SUM/AVG/COUNT, en el primer intento: CAST(columna AS numeric) o "
            "columna::numeric.\n"
            "6. Refiérete ÚNICAMENTE a las tablas listadas en el esquema provisto. "
            "No inventes ni asumas tablas que no estén en la lista.\n"
            "7. Si una consulta falla, intenta una versión más simple (menos JOINs, "
            "menos condiciones) antes de rendirte.\n"
            "8. Los valores de columnas como status, payment_status, etc. están "
            "en INGLÉS y MAYÚSCULAS. Usa los valores exactos que indica el esquema.\n"
            "9. Usa solo columnas de las tablas del esquema; muestra nombres "
            "legibles, no IDs.\n"
            "10. Si el esquema tiene tablas de contra entrega o pagos especiales, "
            "consúltalas según corresponda.\n"
            "Limita resultados con LIMIT."
        )
    elif schema_description and policy.restricted:
        allowed_tables = sorted(policy.allowed_tables())
        if allowed_tables:
            active_system_prompt += (
                "\n\n## Base de datos externa del cliente\n\n"
                "El usuario solo tiene acceso a estas tablas: "
                f"{', '.join(allowed_tables)}.\n"
                "Usa 'ejecutar_consulta' únicamente con esas tablas. "
                "Si la pregunta requiere otra tabla, indica que no tiene acceso."
            )

    # Inyectar la descripción de Google Sheets del cliente si existe
    ext_sheets = getattr(tenant, "external_sheets", None)
    sheets_description = (ext_sheets or {}).get("schema_description")
    if sheets_description and policy.allows("sheets"):
        active_system_prompt += (
            "\n\n## Google Sheets del cliente\n\n"
            "Tienes disponible una hoja de cálculo de Google Sheets con este contenido:\n\n"
            f"{sheets_description}\n\n"
            "Para consultarla usa la herramienta 'consultar_sheet' con el nombre exacto de la hoja. "
            "Aplica 'filtros' por columna cuando el usuario pida un subconjunto. "
            "Usa 'limite' para acotar (default 1000)."
        )

    # Inyectar descripción del Excel del cliente si existe
    ext_excel = getattr(tenant, "external_excel", None)
    excel_description = (ext_excel or {}).get("schema_description")
    if excel_description and (ext_excel or {}).get("access_token") and policy.allows("excel"):
        active_system_prompt += (
            "\n\n## Archivo Excel del cliente (OneDrive/SharePoint)\n\n"
            "Tienes disponible un archivo Excel en OneDrive/SharePoint con este contenido:\n\n"
            f"{excel_description}\n\n"
            "Para consultarlo usa la herramienta 'consultar_excel' con el nombre exacto de la hoja. "
            "Aplica 'filtros' por columna cuando el usuario pida un subconjunto. "
            "Usa 'limite' para acotar (default 1000).\n\n"
            "IMPORTANTE: el Excel NO es parte de la base de datos. Sus hojas NO son "
            "tablas SQL: nunca hagas FROM a una hoja (ej: ASESOR) en una consulta "
            "'ejecutar_consulta'. Los datos del Excel (metas, nombres, períodos) se "
            "usan SOLO como referencia para cruzar con los datos reales de la DB."
        )

    # Inyectar descripción de Alegra si existe
    ext_alegra = getattr(tenant, "external_alegra", None)
    alegra_description = (ext_alegra or {}).get("schema_description")
    if alegra_description and policy.allows("alegra"):
        active_system_prompt += (
            "\n\n" + alegra_description + "\n\n"
            "Para consultarla usa la herramienta 'consultar_alegra' con una descripción "
            "en lenguaje natural de lo que necesitas. Sé específico con fechas y nombres."
        )

    # Inyectar configuración de informes contables si existe
    report_cfg = getattr(tenant, "report_config", None)
    can_use_reports = (
        not policy.restricted
        or policy.allows("external_db")
        or policy.allows("alegra")
        or bool(policy.allowed_tables())
    )
    if report_cfg and report_cfg.get("company_name") and can_use_reports:
        sections_list = ", ".join(report_cfg.get("sections", ["balance", "income", "expenses"]))
        instructions = report_cfg.get("additional_instructions", "")
        prompt = (
            "\n\n## Informes contables personalizados\n\n"
            f"Puedes generar informes contables PDF para {report_cfg['company_name']}. "
            f"Secciones habilitadas: {sections_list}.\n"
        )
        if instructions:
            prompt += f"Instrucciones: {instructions}\n"
        prompt += (
            "Para generar un informe o tablero: (1) consulta los datos con "
            "'ejecutar_consulta' o 'consultar_alegra', (2) organiza los datos en "
            "secciones con título, encabezados y filas, (3) llama "
            "'generar_informe_contable' con el array de secciones y el período. "
            "En el chat web se mostrará como tarjeta HTML con vista previa; en "
            "Telegram se envía como PDF. Si piden un archivo PDF o Excel "
            "descargable, usa 'generar_informe'.\n"
            "Para tableros, arma secciones claras con columnas numéricas y "
            "resúmenes ejecutivos; el sistema genera KPIs y gráficos "
            "automáticamente. Ejemplo de sección: {\"title\": \"Balance General\", "
            "\"headers\": [\"Cuenta\", \"Valor\"], "
            "\"rows\": [[\"Efectivo\", \"$5.000.000\"]], "
            "\"summary\": \"Total activos: $5.000.000\"}"
        )
        active_system_prompt += prompt
    # Inyectar contexto temporal (fechas de hoy/ayer/mes) para que el modelo
    # entienda expresiones relativas sin que el usuario use variables.
    try:
        from mind.scheduler.prompts import build_context
        ctx = build_context(tenant)
        active_system_prompt += (
            "\n\n## Contexto temporal\n"
            f"Hoy es {ctx['fecha_larga']} ({ctx['fecha']}). "
            f"Ayer fue {ctx['ayer']}. Inicio de la semana: {ctx['inicio_semana']}. "
            f"Inicio del mes: {ctx['inicio_mes']}. "
            "Interpreta expresiones relativas ('hoy', 'ayer', 'esta semana', "
            "'este mes', 'el día anterior') usando estas fechas."
        )
    except Exception:
        pass

    # Inyectar base de conocimiento del cliente si tiene información cargada
    try:
        from mind.knowledge.retriever import build_knowledge_context
        knowledge = await build_knowledge_context(
            session, tenant.id, message,
            allowed_sources=policy.allowed if policy.restricted else None,
        )
        if knowledge:
            active_system_prompt += (
                "\n\n## Base de conocimiento del cliente\n\n"
                f"{knowledge}\n\n"
                "Usa esta información cuando sea relevante para responder. "
                "No la contradigas ni inventes datos que no estén en las fuentes."
            )
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
    # --- 3. Construir messages para OpenAI ---
    prompt_ctx = build_prompt(history, active_window)
    truncated = truncate_to_token_limit(prompt_ctx.messages, max_tokens=100_000)

    openai_messages: list[dict[str, Any]] = [
        {"role": "system", "content": active_system_prompt}
    ]
    openai_messages.extend(m.to_openai_dict() for m in truncated)
    openai_messages.append({"role": "user", "content": message})

    tools = get_allowed_tool_schemas(user_permissions, policy)
    # Proveedores de correo/calendario vinculados (para gatear sus tools)
    try:
        from mind.integrations.store import get_active_providers
        email_providers = await get_active_providers(session, tenant.id)
    except Exception:
        email_providers = set()

    # Filtrar tools no configuradas para este tenant
    tenant_ofima = bool(tenant.sqlserver_host)
    tenant_ext_db = bool(tenant.external_db)
    tenant_ext_sheets = bool(tenant.external_sheets)
    tenant_ext_excel = bool(tenant.external_excel and tenant.external_excel.get("access_token"))
    tenant_alegra = bool(tenant.external_alegra and tenant.external_alegra.get("token"))
    ofima_tools = {
        "consultar_ventas", "consultar_ventas_detalle", "consultar_indicadores",
        "consultar_finanzas", "consultar_productos", "consultar_cxp", "generar_informe",
        "catalogo_precios", "stock_celulares", "gangazos", "ventas_recientes",
        "inventario_bodega", "validar_imei", "historial_cliente", "buscar_cliente",
        "direccion_proveedor", "estado_sincronizacion_clientes",
        "inventario_activos", "cliente_completo", "factura_reciente_cliente",
        "medios_pago", "movimientos_contables",
    }
    # Tools de tareas programadas — solo si el tenant tiene OFIMA
    task_tools = {"crear_tarea_programada", "listar_tareas", "eliminar_tarea", "modificar_tarea"}
    # Tools de correo/calendario — solo si hay una cuenta vinculada
    mail_tools = {"correos_recientes", "buscar_correos", "leer_correo", "guardar_borrador_respuesta"}
    calendar_tools = {"eventos_calendario", "proximos_eventos"}
    filtered_tools = []
    for t in tools:
        name = t["function"]["name"]
        if name in ofima_tools and not tenant_ofima:
            continue
        if name in task_tools and not tenant_ofima:
            continue
        if (name in mail_tools or name in calendar_tools) and not email_providers:
            continue
        if name == "ejecutar_consulta" and not tenant_ext_db:
            continue
        if name == "consultar_sheet" and not tenant_ext_sheets:
            continue
        if name == "consultar_excel" and not tenant_ext_excel:
            continue
        if name == "consultar_alegra" and not tenant_alegra:
            continue
        filtered_tools.append(t)
    tools = filtered_tools
    active_system_prompt += "\n\n" + tool_catalog(tools)
    openai_messages[0] = {"role": "system", "content": active_system_prompt}
    logger.info(
        "tenant=%s chat_id=%s permisos=%s tools=%s",
        tenant.slug, chat_id, user_permissions,
        [t["function"]["name"] for t in tools],
    )

    new_messages: list[Message] = [Message(role="user", content=message)]
    file_path: str | None = None
    file_caption: str | None = None
    final_text: str = ""
    usage_prompt_tokens: int = 0
    usage_completion_tokens: int = 0

    # --- 4. Loop de tool-calling ---
    try:
        for cycle in range(active_max_cycles):
            # Forzar tool call en el primer ciclo si hay herramientas disponibles
            first_tool_choice = (
                {"type": "function", "function": {"name": tools[0]["function"]["name"]}}
                if cycle == 0 and tools and len(tools) == 1
                else "auto"
            )
            response = await client.chat.completions.create(
                model=active_model,
                messages=openai_messages,
                tools=tools if tools else None,
                tool_choice=first_tool_choice,
            )

            # Acumular consumo de tokens de esta llamada al LLM
            response_usage = getattr(response, "usage", None)
            if response_usage is not None:
                usage_prompt_tokens += int(getattr(response_usage, "prompt_tokens", 0) or 0)
                usage_completion_tokens += int(
                    getattr(response_usage, "completion_tokens", 0) or 0
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
                    tool_result_str = await dispatch(tool_name, raw_args, user_permissions, policy)
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
                        "mensaje": (
                            "No tienes acceso a esa información. "
                            "Si la necesitas, pide acceso a tu administrador."
                        ),
                    })
                    from mind.auth.data_policy import source_key_for_tool
                    await log_permission_denied(
                        tool_name=tool_name,
                        params=raw_args,
                        reason=str(exc),
                        chat_id=chat_id,
                        user_id=getattr(auth_result.user, "user_id", None),
                        tenant_id=tenant.id,
                        role_id=next(iter(role_ids), None),
                        source_key=source_key_for_tool(tool_name),
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
    if persist_history:
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

    # --- 7. Registrar consumo de tokens y evaluar umbral de alertas ---
    await record_usage(
        tenant_id=tenant.id,
        chat_id=chat_id,
        user_id=user_id,
        username=auth_result.user.username if auth_result.user else None,
        model=active_model,
        prompt_tokens=usage_prompt_tokens,
        completion_tokens=usage_completion_tokens,
        source=source,
    )

    return AgentResult(text=final_text, file_path=file_path, file_caption=file_caption)

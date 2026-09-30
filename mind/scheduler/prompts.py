"""
Motor de prompts programados de Mind.

Cada prompt configurado por el administrador se ejecuta con un cron y envía su
resultado por Telegram al chat/grupo destino. El prompt puede contener
variables de contexto ({{fecha}}, {{ayer}}, {{tienda}}, ...) que se resuelven
en el momento de la ejecución, y se alimenta de la base de conocimiento y los
MCPs conectados del cliente.

Los jobs se registran con el prefijo de id "prompt:" para no interferir con
las tareas programadas de los usuarios (que usan otro id).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

JOB_PREFIX = "prompt:"
DEFAULT_TZ = "America/Bogota"

# 0 = lunes ... 6 = domingo (nombres, sin ambigüedad numérica de cron)
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_ES_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_ES_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


# ── Cron ──────────────────────────────────────────────────────────────────────

def compose_cron(
    frequency: str,
    hour: int = 8,
    minute: int = 0,
    weekday: int = 0,
    custom: str | None = None,
) -> str:
    """
    Convierte una frecuencia amigable en una expresión cron de 5 campos.
    - daily:    minuto hora * * *
    - weekly:   minuto hora * * <día>
    - custom:   usa `custom` tal cual
    """
    frequency = (frequency or "daily").lower()
    if frequency == "custom":
        expr = (custom or "").strip()
        if not expr:
            raise ValueError("La expresión cron es obligatoria para frecuencia personalizada.")
        return expr

    h = max(0, min(23, int(hour)))
    m = max(0, min(59, int(minute)))
    if frequency == "weekly":
        wd = WEEKDAYS[max(0, min(6, int(weekday)))]
        return f"{m} {h} * * {wd}"
    return f"{m} {h} * * *"


# ── Variables de contexto ─────────────────────────────────────────────────────

def build_context(tenant, now: datetime | None = None) -> dict[str, str]:
    """Variables disponibles en los prompts ({{clave}})."""
    tz = ZoneInfo(DEFAULT_TZ)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    today = now.date()
    monday = today - timedelta(days=today.weekday())
    first_of_month = today.replace(day=1)

    return {
        "fecha": today.isoformat(),
        "hoy": today.isoformat(),
        "ayer": (today - timedelta(days=1)).isoformat(),
        "manana": (today + timedelta(days=1)).isoformat(),
        "hora": now.strftime("%H:%M"),
        "dia_semana": _ES_DIAS[today.weekday()],
        "fecha_larga": (
            f"{_ES_DIAS[today.weekday()]}, {today.day} de "
            f"{_ES_MESES[today.month - 1]} de {today.year}"
        ),
        "inicio_semana": monday.isoformat(),
        "inicio_mes": first_of_month.isoformat(),
        "mes": f"{today.month:02d}",
        "anio": str(today.year),
        "tienda": getattr(tenant, "name", "") or "",
    }


def render_prompt(template: str, context: dict[str, str]) -> str:
    """Reemplaza {{variable}} por su valor. Las variables desconocidas se dejan igual."""
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        value = context.get(key)
        return str(value) if value is not None else match.group(0)

    return _VAR_RE.sub(_replace, template or "")


def available_variables() -> list[dict[str, str]]:
    """Metadatos de variables para mostrarlas en el panel."""
    return [
        {"key": "fecha", "desc": "Fecha de hoy (YYYY-MM-DD)"},
        {"key": "ayer", "desc": "Fecha de ayer (YYYY-MM-DD)"},
        {"key": "manana", "desc": "Fecha de mañana (YYYY-MM-DD)"},
        {"key": "dia_semana", "desc": "Nombre del día de hoy"},
        {"key": "fecha_larga", "desc": "Fecha larga en español"},
        {"key": "hora", "desc": "Hora actual (HH:MM)"},
        {"key": "inicio_semana", "desc": "Lunes de la semana actual"},
        {"key": "inicio_mes", "desc": "Primer día del mes actual"},
        {"key": "mes", "desc": "Mes actual (MM)"},
        {"key": "anio", "desc": "Año actual"},
        {"key": "tienda", "desc": "Nombre del cliente/tienda"},
    ]


# ── Registro de jobs ──────────────────────────────────────────────────────────

def sync_prompt_job(prompt) -> None:
    """Registra, reprograma o elimina el job del prompt según su estado."""
    from mind.scheduler.manager import get_scheduler

    sched = get_scheduler()
    job_id = f"{JOB_PREFIX}{prompt.id}"

    if not prompt.is_active:
        try:
            sched.remove_job(job_id)
        except Exception:
            pass
        return

    trigger = CronTrigger.from_crontab(
        prompt.cron_expression, timezone=prompt.timezone or DEFAULT_TZ
    )
    sched.add_job(
        _execute_prompt,
        trigger=trigger,
        id=job_id,
        args=[prompt.id, prompt.tenant_id],
        replace_existing=True,
        name=(prompt.name or f"Prompt {prompt.id}")[:100],
    )


def remove_prompt_job(prompt_id: int) -> None:
    from mind.scheduler.manager import get_scheduler
    try:
        get_scheduler().remove_job(f"{JOB_PREFIX}{prompt_id}")
    except Exception:
        pass


async def register_all_prompt_jobs() -> None:
    """Carga todos los prompts activos al iniciar la app y limpia jobs obsoletos."""
    from sqlalchemy import select
    from mind.db.base import _session_factory
    from mind.db.models import ScheduledPrompt
    from mind.scheduler.manager import get_scheduler

    if _session_factory is None:
        return

    async with _session_factory() as session:
        prompts = (await session.execute(
            select(ScheduledPrompt).where(ScheduledPrompt.is_active.is_(True))
        )).scalars().all()

    active_ids: set[str] = set()
    for p in prompts:
        try:
            sync_prompt_job(p)
            active_ids.add(f"{JOB_PREFIX}{p.id}")
        except Exception as exc:
            logger.warning("No se pudo registrar prompt programado id=%s: %s", p.id, exc)

    sched = get_scheduler()
    for job in sched.get_jobs():
        if job.id.startswith(JOB_PREFIX) and job.id not in active_ids:
            try:
                sched.remove_job(job.id)
            except Exception:
                pass

    logger.info("Prompts programados registrados: %d", len(active_ids))


# ── Ejecución ─────────────────────────────────────────────────────────────────

async def execute_prompt(prompt_id: int, tenant_id: int, *, send: bool = True) -> dict:
    """
    Ejecuta un prompt programado: renderiza variables, corre el agente
    (con base de conocimiento + MCPs) y envía el resultado por Telegram.
    """
    from sqlalchemy import select
    from mind.db.base import _session_factory
    from mind.db.models import ScheduledPrompt, User
    from mind.tenants.context import set_tenant
    from mind.tenants.resolver import resolve_by_id

    if _session_factory is None:
        return {"ok": False, "error": "Base de datos no disponible."}

    tenant = resolve_by_id(tenant_id)
    if tenant is None:
        return {"ok": False, "error": "Tenant no encontrado en caché."}

    async with _session_factory() as session:
        sp = (await session.execute(
            select(ScheduledPrompt).where(
                ScheduledPrompt.id == prompt_id,
                ScheduledPrompt.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
        if sp is None:
            return {"ok": False, "error": "Prompt no encontrado."}

        set_tenant(tenant)
        rendered = render_prompt(sp.prompt, build_context(tenant))

        user = (await session.execute(
            select(User).where(User.chat_id == sp.chat_id, User.tenant_id == tenant_id)
        )).scalar_one_or_none()

        from mind.auth.authorization import AuthResult, Permission
        auth = AuthResult(allowed=True, user=user, role=None)
        # Los prompts programados se configuran por administradores: corren con
        # todos los permisos disponibles del tenant.
        full_permissions = frozenset(p.value for p in Permission)

        text = ""
        try:
            from mind.agent.orchestrator import process
            result = await process(
                message=rendered,
                chat_id=sp.chat_id,
                tenant=tenant,
                auth_result=auth,
                session=session,
                source="scheduled_prompt",
                forced_permissions=full_permissions,
            )
            text = result.text or ""
        except Exception as exc:
            logger.error(
                "Error ejecutando prompt programado id=%s tenant=%s: %s",
                prompt_id, tenant.slug, exc,
            )
            sp.last_run_at = datetime.now(timezone.utc)
            sp.last_status = "error"
            sp.last_error = str(exc)[:500]
            await session.commit()
            return {"ok": False, "error": str(exc), "rendered_prompt": rendered}

        send_error: str | None = None
        if send:
            try:
                from mind.telegram.bot import send_text
                await send_text(sp.chat_id, text, tenant.bot_token)
            except Exception as exc:
                logger.warning(
                    "Prompt id=%s generado pero falló el envío por Telegram: %s",
                    prompt_id, exc,
                )
                send_error = f"No se pudo enviar por Telegram: {exc}"

        sp.last_run_at = datetime.now(timezone.utc)
        sp.last_status = "error" if send_error else "success"
        sp.last_error = send_error[:500] if send_error else None
        await session.commit()

    try:
        from mind.audit.logger import AuditRecord, log_interaction
        await log_interaction(AuditRecord(
            event_type="scheduled_prompt",
            chat_id=sp.chat_id,
            tenant_id=tenant_id,
            request_content=rendered[:1000],
            response_content=text[:2000],
            status="error" if send_error else "success",
            error_description=send_error,
        ))
    except Exception:
        pass

    if send_error:
        return {"ok": False, "error": send_error, "text": text, "rendered_prompt": rendered}
    return {"ok": True, "text": text, "rendered_prompt": rendered}


async def _execute_prompt(prompt_id: int, tenant_id: int) -> None:
    """Callback ejecutado por APScheduler."""
    await execute_prompt(prompt_id, tenant_id, send=True)

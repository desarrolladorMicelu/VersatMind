"""
Scheduler de tareas programadas con APScheduler 3.x.
Multi-tenant: cada job lleva su tenant_id en los args.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.job import Job

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    if _scheduler is None:
        raise RuntimeError("Scheduler no inicializado. Llama a init_scheduler() primero.")
    return _scheduler


def init_scheduler(database_url_sync: str) -> AsyncIOScheduler:
    """Inicializa el AsyncIOScheduler con SQLAlchemyJobStore."""
    global _scheduler
    jobstores = {"default": SQLAlchemyJobStore(url=database_url_sync)}
    _scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        timezone="America/Bogota",
    )
    return _scheduler


def validate_cron_expression(expr: str) -> dict[str, Any]:
    try:
        parts = expr.strip().split()
        if len(parts) not in (5, 6):
            return {
                "valid": False,
                "field": "expresion_cron",
                "message": f"La expresión cron debe tener 5 o 6 campos, tiene {len(parts)}.",
            }
        CronTrigger.from_crontab(expr.strip() if len(parts) == 5 else " ".join(parts[:5]))
        return {"valid": True}
    except Exception as exc:
        return {"valid": False, "field": "expresion_cron", "message": f"Expresión cron inválida: {exc}"}


def validate_cron_min_interval(expr: str) -> dict[str, Any]:
    try:
        trigger = CronTrigger.from_crontab(expr.strip())
        now = datetime.now(timezone.utc)
        t1 = trigger.get_next_fire_time(None, now)
        t2 = trigger.get_next_fire_time(t1, t1)
        if t1 is None or t2 is None:
            return {"valid": True}
        diff_minutes = (t2 - t1).total_seconds() / 60
        if diff_minutes < 5:
            return {
                "valid": False,
                "field": "expresion_cron",
                "message": (
                    f"El intervalo mínimo entre ejecuciones es 5 minutos. "
                    f"La expresión genera ejecuciones cada {diff_minutes:.1f} minutos."
                ),
            }
        return {"valid": True}
    except Exception:
        return {"valid": False, "field": "expresion_cron", "message": "Expresión cron inválida."}


async def add_job(
    chat_id: int,
    tenant_id: int,
    description: str,
    cron_expression: str,
    session,
) -> dict[str, Any]:
    """Agrega un job al scheduler y persiste en scheduled_tasks."""
    from mind.db.models import ScheduledTask

    cron_valid = validate_cron_expression(cron_expression)
    if not cron_valid["valid"]:
        return {"error": True, **cron_valid}

    interval_valid = validate_cron_min_interval(cron_expression)
    if not interval_valid["valid"]:
        return {"error": True, **interval_valid}

    task_id = str(uuid.uuid4())
    sched = get_scheduler()

    try:
        trigger = CronTrigger.from_crontab(cron_expression, timezone="America/Bogota")
        job: Job = sched.add_job(
            _execute_task,
            trigger=trigger,
            id=task_id,
            args=[task_id, tenant_id],
            name=description[:100],
            replace_existing=True,
        )
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
    except Exception as exc:
        return {"error": True, "message": f"Error al programar la tarea: {exc}"}

    task = ScheduledTask(
        id=task_id,
        chat_id=chat_id,
        tenant_id=tenant_id,
        description=description,
        cron_expression=cron_expression,
        timezone="America/Bogota",
        status="active",
    )
    session.add(task)
    await session.flush()

    return {
        "error": False,
        "task_id": task_id,
        "next_execution": next_run,
        "description": description,
        "cron_expression": cron_expression,
    }


async def remove_job(task_id: str, chat_id: int, tenant_id: int, session) -> dict[str, Any]:
    from sqlalchemy import select, update
    from mind.db.models import ScheduledTask

    stmt = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.chat_id == chat_id,
        ScheduledTask.tenant_id == tenant_id,
        ScheduledTask.status == "active",
    )
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if task is None:
        return {"error": True, "message": f"Tarea {task_id!r} no encontrada."}

    await session.execute(
        update(ScheduledTask).where(ScheduledTask.id == task_id).values(status="inactive")
    )
    await session.flush()

    sched = get_scheduler()
    try:
        sched.remove_job(task_id)
    except Exception:
        pass

    return {"error": False, "task_id": task_id, "message": f"Tarea {task_id!r} eliminada correctamente."}


async def list_jobs(chat_id: int, tenant_id: int, session) -> dict[str, Any]:
    from sqlalchemy import select
    from mind.db.models import ScheduledTask

    stmt = select(ScheduledTask).where(
        ScheduledTask.chat_id == chat_id,
        ScheduledTask.tenant_id == tenant_id,
        ScheduledTask.status == "active",
    ).order_by(ScheduledTask.created_at.desc())

    result = await session.execute(stmt)
    tasks = result.scalars().all()

    sched = get_scheduler()
    task_list = []
    for t in tasks:
        try:
            job = sched.get_job(t.id)
            next_run = job.next_run_time.isoformat() if job and job.next_run_time else "N/A"
        except Exception:
            next_run = "N/A"
        task_list.append({
            "id": t.id,
            "descripcion": t.description,
            "expresion_cron": t.cron_expression,
            "proxima_ejecucion": next_run,
            "estado": t.status,
        })

    return {"error": False, "tareas": task_list, "total": len(task_list)}


async def modify_job(
    task_id: str,
    chat_id: int,
    tenant_id: int,
    session,
    nueva_descripcion: str | None = None,
    nueva_expresion_cron: str | None = None,
) -> dict[str, Any]:
    from sqlalchemy import select, update
    from mind.db.models import ScheduledTask

    stmt = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.chat_id == chat_id,
        ScheduledTask.tenant_id == tenant_id,
        ScheduledTask.status == "active",
    )
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if task is None:
        return {"error": True, "message": f"Tarea {task_id!r} no encontrada."}

    updates: dict = {}
    if nueva_descripcion:
        updates["description"] = nueva_descripcion

    if nueva_expresion_cron:
        cron_valid = validate_cron_expression(nueva_expresion_cron)
        if not cron_valid["valid"]:
            return {"error": True, **cron_valid}
        interval_valid = validate_cron_min_interval(nueva_expresion_cron)
        if not interval_valid["valid"]:
            return {"error": True, **interval_valid}
        updates["cron_expression"] = nueva_expresion_cron
        sched = get_scheduler()
        try:
            trigger = CronTrigger.from_crontab(nueva_expresion_cron, timezone="America/Bogota")
            sched.reschedule_job(task_id, trigger=trigger)
        except Exception as exc:
            return {"error": True, "message": f"Error al reprogramar: {exc}"}

    if updates:
        await session.execute(
            update(ScheduledTask).where(ScheduledTask.id == task_id).values(**updates)
        )
        await session.flush()

    return {"error": False, "task_id": task_id, "message": "Tarea modificada correctamente."}


async def _execute_task(task_id: str, tenant_id: int) -> None:
    """Callback ejecutado por APScheduler. Establece el contexto del tenant antes de correr."""
    from mind.db.base import _session_factory
    from mind.db.models import ScheduledTask, User
    from mind.audit.logger import AuditRecord, log_interaction
    from mind.tenants.resolver import resolve_by_id
    from mind.tenants.context import set_tenant
    from sqlalchemy import select, update

    if _session_factory is None:
        logger.error("_execute_task: session_factory no disponible task_id=%s", task_id)
        return

    tenant = resolve_by_id(tenant_id)
    if tenant is None:
        logger.error("_execute_task: tenant_id=%s no encontrado en caché", tenant_id)
        return

    # Función de envío para este tenant específico
    from mind.telegram.bot import send_text as _send_text

    async def _send(chat_id: int, text: str) -> None:
        await _send_text(chat_id, text, tenant.bot_token)

    async with _session_factory() as session:
        stmt = select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.tenant_id == tenant_id,
            ScheduledTask.status == "active",
        )
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()

        if task is None:
            logger.warning("_execute_task: tarea %s no encontrada o inactiva", task_id)
            return

        chat_id = task.chat_id
        logger.info("Ejecutando tarea id=%s tenant=%s chat_id=%s", task_id, tenant.slug, chat_id)

        # Establecer contexto del tenant
        set_tenant(tenant)

        try:
            from mind.auth.authorization import AuthResult
            user_stmt = select(User).where(
                User.chat_id == chat_id,
                User.tenant_id == tenant_id,
            )
            user_result = await session.execute(user_stmt)
            user = user_result.scalar_one_or_none()

            auth = AuthResult(allowed=True, user=user)

            from mind.agent.orchestrator import process
            agent_result = await process(
                message=task.description,
                chat_id=chat_id,
                tenant=tenant,
                auth_result=auth,
                session=session,
            )

            await _send(chat_id, f"⏰ *Tarea programada*\n\n{agent_result.text}")

            await session.execute(
                update(ScheduledTask)
                .where(ScheduledTask.id == task_id)
                .values(last_execution_at=datetime.now(timezone.utc))
            )
            await session.commit()

            await log_interaction(AuditRecord(
                event_type="scheduler",
                chat_id=chat_id,
                tenant_id=tenant_id,
                request_content=task.description,
                response_content=agent_result.text[:1000],
                status="success",
            ))

        except Exception as exc:
            logger.error("Error ejecutando tarea %s tenant=%s: %s", task_id, tenant.slug, exc)
            try:
                await _send(
                    chat_id,
                    f"⚠️ La tarea programada '{task.description}' falló: {type(exc).__name__}",
                )
            except Exception:
                pass
            await log_interaction(AuditRecord(
                event_type="scheduler",
                chat_id=chat_id,
                tenant_id=tenant_id,
                request_content=task.description,
                status="error",
                error_description=str(exc)[:500],
            ))

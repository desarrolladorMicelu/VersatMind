"""
Scheduler de tareas programadas con APScheduler 3.x.
Persiste jobs en PostgreSQL con SQLAlchemyJobStore.
Requisitos: 7.1-7.11
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, UTC
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.job import Job

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_bot_send_text_fn = None  # se inyecta desde main.py


def set_bot_send_fn(fn) -> None:
    """Inyecta la función de envío de Telegram. Llamar desde main.py."""
    global _bot_send_text_fn
    _bot_send_text_fn = fn


def get_scheduler() -> AsyncIOScheduler:
    if _scheduler is None:
        raise RuntimeError("Scheduler no inicializado. Llama a init_scheduler() primero.")
    return _scheduler


def init_scheduler(database_url_sync: str) -> AsyncIOScheduler:
    """
    Inicializa el AsyncIOScheduler con SQLAlchemyJobStore.
    Llamar desde lifespan de FastAPI.
    Requisito: 7.2, 7.8
    """
    global _scheduler
    jobstores = {
        "default": SQLAlchemyJobStore(url=database_url_sync)
    }
    _scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        timezone="America/Bogota",
    )
    return _scheduler


def validate_cron_expression(expr: str) -> dict[str, Any]:
    """
    Valida una expresión cron de 5 campos.
    Función pura para property-based testing.
    Propiedad 17 — Valida: Requisito 7.7
    """
    try:
        parts = expr.strip().split()
        if len(parts) not in (5, 6):
            return {
                "valid": False,
                "field": "expresion_cron",
                "message": f"La expresión cron debe tener 5 o 6 campos, tiene {len(parts)}.",
            }
        # Intentar parsear con APScheduler para validación completa
        CronTrigger.from_crontab(expr.strip() if len(parts) == 5 else " ".join(parts[:5]))
        return {"valid": True}
    except Exception as exc:
        return {
            "valid": False,
            "field": "expresion_cron",
            "message": f"Expresión cron inválida: {exc}",
        }


def validate_cron_min_interval(expr: str) -> dict[str, Any]:
    """
    Verifica que el intervalo mínimo de ejecución sea ≥ 5 minutos.
    Propiedad 18 — Valida: Requisito 7.11
    """
    try:
        trigger = CronTrigger.from_crontab(expr.strip())
        now = datetime.now(UTC)
        t1 = trigger.get_next_fire_time(None, now)
        t2 = trigger.get_next_fire_time(t1, t1)
        if t1 is None or t2 is None:
            return {"valid": True}  # no se puede calcular → aceptar
        diff_minutes = (t2 - t1).total_seconds() / 60
        if diff_minutes < 5:
            return {
                "valid": False,
                "field": "expresion_cron",
                "message": f"El intervalo mínimo entre ejecuciones es 5 minutos. "
                           f"La expresión genera ejecuciones cada {diff_minutes:.1f} minutos.",
            }
        return {"valid": True}
    except Exception:
        return {"valid": False, "field": "expresion_cron", "message": "Expresión cron inválida."}


async def add_job(
    chat_id: int,
    description: str,
    cron_expression: str,
    session,
) -> dict[str, Any]:
    """
    Agrega un job al scheduler y persiste en scheduled_tasks.
    Requisitos: 7.1, 7.2
    """
    from mind.db.models import ScheduledTask

    # Validar cron
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
            args=[task_id],
            name=description[:100],
            replace_existing=True,
        )
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
    except Exception as exc:
        return {"error": True, "message": f"Error al programar la tarea: {exc}"}

    # Persistir en la tabla scheduled_tasks
    task = ScheduledTask(
        id=task_id,
        chat_id=chat_id,
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


async def remove_job(task_id: str, chat_id: int, session) -> dict[str, Any]:
    """
    Marca la tarea como inactiva y elimina el job del scheduler.
    Requisitos: 7.9, 7.10
    """
    from sqlalchemy import select, update
    from mind.db.models import ScheduledTask

    stmt = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.chat_id == chat_id,
        ScheduledTask.status == "active",
    )
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if task is None:
        return {"error": True, "message": f"Tarea {task_id!r} no encontrada."}

    # Marcar inactiva en DB
    upd = (
        update(ScheduledTask)
        .where(ScheduledTask.id == task_id)
        .values(status="inactive")
    )
    await session.execute(upd)
    await session.flush()

    # Eliminar del scheduler
    sched = get_scheduler()
    try:
        sched.remove_job(task_id)
    except Exception:
        pass  # ya no existía en el scheduler

    return {
        "error": False,
        "task_id": task_id,
        "message": f"Tarea {task_id!r} eliminada correctamente.",
    }


async def list_jobs(chat_id: int, session) -> dict[str, Any]:
    """Retorna las tareas activas del usuario. Requisito: 7.5"""
    from sqlalchemy import select
    from mind.db.models import ScheduledTask

    stmt = select(ScheduledTask).where(
        ScheduledTask.chat_id == chat_id,
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
    session,
    nueva_descripcion: str | None = None,
    nueva_expresion_cron: str | None = None,
) -> dict[str, Any]:
    """Modifica descripción y/o cron de una tarea. Requisito: 7.4"""
    from sqlalchemy import select, update
    from mind.db.models import ScheduledTask

    stmt = select(ScheduledTask).where(
        ScheduledTask.id == task_id,
        ScheduledTask.chat_id == chat_id,
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
        # Reprogramar en APScheduler
        sched = get_scheduler()
        try:
            trigger = CronTrigger.from_crontab(nueva_expresion_cron, timezone="America/Bogota")
            sched.reschedule_job(task_id, trigger=trigger)
        except Exception as exc:
            return {"error": True, "message": f"Error al reprogramar: {exc}"}

    if updates:
        upd = update(ScheduledTask).where(ScheduledTask.id == task_id).values(**updates)
        await session.execute(upd)
        await session.flush()

    return {"error": False, "task_id": task_id, "message": "Tarea modificada correctamente."}


async def _execute_task(task_id: str) -> None:
    """
    Callback ejecutado por APScheduler cuando llega el momento.
    Carga la tarea, la ejecuta y envía resultado al chat_id.
    Requisito: 7.3, 7.6
    """
    from mind.db.base import _session_factory
    from mind.db.models import ScheduledTask
    from mind.audit.logger import AuditRecord, log_interaction
    from sqlalchemy import select, update

    if _session_factory is None:
        logger.error("_execute_task: session_factory no disponible para task_id=%s", task_id)
        return

    async with _session_factory() as session:
        stmt = select(ScheduledTask).where(
            ScheduledTask.id == task_id,
            ScheduledTask.status == "active",
        )
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()

        if task is None:
            logger.warning("_execute_task: tarea %s no encontrada o inactiva", task_id)
            return

        chat_id = task.chat_id
        logger.info("Ejecutando tarea programada id=%s chat_id=%s", task_id, chat_id)

        try:
            # Ejecutar la descripción como un nuevo mensaje al agente
            from mind.auth.authorization import AuthResult
            # Tarea programada usa permisos completos del sistema
            from mind.db.models import User, Role
            user_stmt = select(User).where(User.chat_id == chat_id)
            user_result = await session.execute(user_stmt)
            user = user_result.scalar_one_or_none()

            auth = AuthResult(allowed=True, user=user)

            from mind.agent.orchestrator import process
            agent_result = await process(
                message=task.description,
                chat_id=chat_id,
                auth_result=auth,
                session=session,
            )

            # Enviar resultado por Telegram
            if _bot_send_text_fn:
                await _bot_send_text_fn(chat_id, f"⏰ *Tarea programada*\n\n{agent_result.text}")

            # Actualizar last_execution_at
            upd = (
                update(ScheduledTask)
                .where(ScheduledTask.id == task_id)
                .values(last_execution_at=datetime.now(UTC))
            )
            await session.execute(upd)
            await session.commit()

            await log_interaction(AuditRecord(
                event_type="scheduler",
                chat_id=chat_id,
                request_content=task.description,
                response_content=agent_result.text[:1000],
                status="success",
            ))

        except Exception as exc:
            logger.error("Error ejecutando tarea %s: %s", task_id, exc)
            if _bot_send_text_fn:
                try:
                    await _bot_send_text_fn(
                        chat_id,
                        f"⚠️ La tarea programada '{task.description}' falló: {type(exc).__name__}"
                    )
                except Exception:
                    pass
            await log_interaction(AuditRecord(
                event_type="scheduler",
                chat_id=chat_id,
                request_content=task.description,
                status="error",
                error_description=str(exc)[:500],
            ))

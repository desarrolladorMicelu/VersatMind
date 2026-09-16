"""
Herramientas de gestión del scheduler para el agente Mind.
Requisitos: 7.1, 7.4, 7.5, 7.7, 7.10, 7.11
"""
from __future__ import annotations

from typing import Any

from mind.scheduler.manager import (
    validate_cron_expression,
    validate_cron_min_interval,
    add_job,
    remove_job,
    list_jobs,
    modify_job,
)


async def crear_tarea_programada(
    descripcion: str,
    expresion_cron: str,
    chat_id: int,
) -> dict[str, Any]:
    """
    Crea una tarea programada recurrente.
    Requisito: 7.1, 7.2, 7.7, 7.11
    """
    from mind.db.base import _session_factory

    if _session_factory is None:
        return {"error": True, "mensaje": "Base de datos no disponible."}

    async with _session_factory() as session:
        result = await add_job(
            chat_id=chat_id,
            description=descripcion,
            cron_expression=expresion_cron,
            session=session,
        )
        if not result.get("error"):
            await session.commit()
    return result


async def listar_tareas(chat_id: int) -> dict[str, Any]:
    """Lista tareas programadas activas del usuario. Requisito: 7.5"""
    from mind.db.base import _session_factory

    if _session_factory is None:
        return {"error": True, "mensaje": "Base de datos no disponible."}

    async with _session_factory() as session:
        return await list_jobs(chat_id=chat_id, session=session)


async def eliminar_tarea(task_id: str, chat_id: int) -> dict[str, Any]:
    """Elimina (desactiva) una tarea programada. Requisito: 7.10"""
    from mind.db.base import _session_factory

    if _session_factory is None:
        return {"error": True, "mensaje": "Base de datos no disponible."}

    async with _session_factory() as session:
        result = await remove_job(task_id=task_id, chat_id=chat_id, session=session)
        if not result.get("error"):
            await session.commit()
    return result


async def modificar_tarea(
    task_id: str,
    chat_id: int,
    nueva_descripcion: str | None = None,
    nueva_expresion_cron: str | None = None,
) -> dict[str, Any]:
    """Modifica descripción o cron de una tarea. Requisito: 7.4"""
    from mind.db.base import _session_factory

    if _session_factory is None:
        return {"error": True, "mensaje": "Base de datos no disponible."}

    async with _session_factory() as session:
        result = await modify_job(
            task_id=task_id,
            chat_id=chat_id,
            session=session,
            nueva_descripcion=nueva_descripcion,
            nueva_expresion_cron=nueva_expresion_cron,
        )
        if not result.get("error"):
            await session.commit()
    return result

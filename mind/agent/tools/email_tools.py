"""
Herramientas de correo y calendario para el agente (Outlook / Google).

Resuelven la conexión OAuth activa del tenant en contexto y operan contra
Microsoft Graph o las APIs de Google. Solo lectura + borradores (sin envío).
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

BOGOTA = ZoneInfo("America/Bogota")


def _fail(where: str, exc: Exception) -> dict[str, Any]:
    logger.error("Error en %s: %s\n%s", where, exc, traceback.format_exc())
    return {"error": True, "mensaje": f"{type(exc).__name__}: {exc}"}


def _slim(m: dict) -> dict:
    return {
        "id": m.get("id"),
        "asunto": m.get("subject"),
        "de": m.get("from"),
        "fecha": m.get("date"),
        "resumen": (m.get("preview") or "")[:300],
        "leido": m.get("is_read"),
    }


async def _resolve_connection(session, proveedor: str | None):
    from mind.tenants.context import get_tenant
    from mind.integrations.store import get_active_connection, get_active_providers

    tenant = get_tenant()
    providers = await get_active_providers(session, tenant.id)
    if not providers:
        raise RuntimeError(
            "Este cliente no tiene cuentas de correo/calendario vinculadas. "
            "Vincúlalas desde el panel → Integraciones."
        )
    if proveedor:
        p = proveedor.strip().lower()
        if p not in providers:
            raise RuntimeError(
                f"El proveedor '{proveedor}' no está vinculado. "
                f"Disponibles: {', '.join(sorted(providers))}."
            )
    elif len(providers) == 1:
        p = next(iter(providers))
    else:
        raise RuntimeError(
            f"Hay varias cuentas vinculadas ({', '.join(sorted(providers))}). "
            "Indica el parámetro 'proveedor'."
        )
    conn = await get_active_connection(session, tenant.id, p)
    if conn is None:
        raise RuntimeError(f"No hay conexión activa de {p}.")
    return conn


async def correos_recientes(proveedor: str | None = None, limite: int = 10) -> dict[str, Any]:
    """Lista los correos más recientes de la bandeja de entrada."""
    from mind.db.base import _session_factory
    if _session_factory is None:
        return {"error": True, "mensaje": "Base de datos no disponible."}
    try:
        async with _session_factory() as session:
            conn = await _resolve_connection(session, proveedor)
            from mind.integrations.mail import list_recent
            msgs = await list_recent(session, conn, limit=max(1, min(int(limite or 10), 25)))
            return {
                "error": False, "proveedor": conn.provider, "cuenta": conn.account_email,
                "correos": [_slim(m) for m in msgs], "total": len(msgs),
            }
    except Exception as exc:
        return _fail("correos_recientes", exc)


async def buscar_correos(consulta: str, proveedor: str | None = None, limite: int = 10) -> dict[str, Any]:
    """Busca correos por texto (asunto, remitente o contenido)."""
    from mind.db.base import _session_factory
    if _session_factory is None:
        return {"error": True, "mensaje": "Base de datos no disponible."}
    try:
        async with _session_factory() as session:
            conn = await _resolve_connection(session, proveedor)
            from mind.integrations.mail import search
            msgs = await search(session, conn, consulta, limit=max(1, min(int(limite or 10), 25)))
            return {
                "error": False, "proveedor": conn.provider, "consulta": consulta,
                "correos": [_slim(m) for m in msgs], "total": len(msgs),
            }
    except Exception as exc:
        return _fail("buscar_correos", exc)


async def leer_correo(correo_id: str, proveedor: str | None = None) -> dict[str, Any]:
    """Lee el contenido completo de un correo por su id."""
    from mind.db.base import _session_factory
    if _session_factory is None:
        return {"error": True, "mensaje": "Base de datos no disponible."}
    try:
        async with _session_factory() as session:
            conn = await _resolve_connection(session, proveedor)
            from mind.integrations.mail import get_message
            m = await get_message(session, conn, correo_id)
            return {
                "error": False, "proveedor": conn.provider,
                "correo": {
                    "id": m.get("id"), "asunto": m.get("subject"), "de": m.get("from"),
                    "para": m.get("to"), "fecha": m.get("date"), "cuerpo": m.get("body"),
                },
            }
    except Exception as exc:
        return _fail("leer_correo", exc)


async def guardar_borrador_respuesta(
    correo_id: str, cuerpo: str, proveedor: str | None = None
) -> dict[str, Any]:
    """Guarda un borrador de respuesta en la bandeja (no lo envía)."""
    from mind.db.base import _session_factory
    if _session_factory is None:
        return {"error": True, "mensaje": "Base de datos no disponible."}
    try:
        async with _session_factory() as session:
            conn = await _resolve_connection(session, proveedor)
            from mind.integrations.drafts import create_reply_draft
            result = await create_reply_draft(session, conn, correo_id, cuerpo)
            return {"error": False, **result}
    except Exception as exc:
        return _fail("guardar_borrador_respuesta", exc)


def _range_from(inicio: str | None, fin: str | None) -> tuple[datetime, datetime]:
    """Rango en hora Bogotá. Sin argumentos: hoy."""
    if inicio:
        try:
            ds = datetime.fromisoformat(inicio).date()
        except ValueError:
            ds = datetime.now(BOGOTA).date()
    else:
        ds = datetime.now(BOGOTA).date()
    if fin:
        try:
            de = datetime.fromisoformat(fin).date()
        except ValueError:
            de = ds
    else:
        de = ds
    start = datetime.combine(ds, time.min, tzinfo=BOGOTA)
    end = datetime.combine(de + timedelta(days=1), time.min, tzinfo=BOGOTA)
    return start, end


async def eventos_calendario(
    inicio: str | None = None, fin: str | None = None,
    proveedor: str | None = None, limite: int = 20,
) -> dict[str, Any]:
    """Lista eventos de calendario en un rango de fechas (por defecto, hoy)."""
    from mind.db.base import _session_factory
    if _session_factory is None:
        return {"error": True, "mensaje": "Base de datos no disponible."}
    try:
        start, end = _range_from(inicio, fin)
        async with _session_factory() as session:
            conn = await _resolve_connection(session, proveedor)
            from mind.integrations.calendar import list_events
            events = await list_events(session, conn, start, end, limit=max(1, min(int(limite or 20), 50)))
            return {
                "error": False, "proveedor": conn.provider,
                "desde": start.isoformat(), "hasta": end.isoformat(),
                "eventos": events, "total": len(events),
            }
    except Exception as exc:
        return _fail("eventos_calendario", exc)


async def proximos_eventos(dias: int = 7, proveedor: str | None = None) -> dict[str, Any]:
    """Lista los próximos eventos desde ahora en los siguientes N días."""
    from mind.db.base import _session_factory
    if _session_factory is None:
        return {"error": True, "mensaje": "Base de datos no disponible."}
    try:
        dias = max(1, min(int(dias or 7), 60))
        start = datetime.now(BOGOTA)
        end = start + timedelta(days=dias)
        async with _session_factory() as session:
            conn = await _resolve_connection(session, proveedor)
            from mind.integrations.calendar import list_events
            events = await list_events(session, conn, start, end, limit=30)
            return {
                "error": False, "proveedor": conn.provider, "dias": dias,
                "eventos": events, "total": len(events),
            }
    except Exception as exc:
        return _fail("proximos_eventos", exc)

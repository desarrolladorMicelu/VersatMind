"""Tools de consulta para fuentes JSON R2."""
from __future__ import annotations

from typing import Any

from mind.data.json_source import (
    JsonSourceError,
    load_source,
    query_historial,
    query_precios,
    summary_historial,
    summary_precios,
)
from mind.tenants.context import get_tenant_or_none


def _tenant():
    tenant = get_tenant_or_none()
    if tenant is None:
        raise JsonSourceError("No hay un cliente activo para consultar el JSON.")
    return tenant


async def consultar_precios_exito(
    codigo: str | None = None,
    codigo_ofim: str | None = None,
    nombre_contiene: str | None = None,
    vendedor: str | None = None,
    solo_con_micelu: bool = False,
    precio_min: float | None = None,
    precio_max: float | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Consulta precios de competencia desde el JSON de Éxito."""
    try:
        records = await load_source(_tenant(), "precios")
        return {
            "error": False,
            "fuente": "precios",
            **query_precios(
                records,
                codigo=codigo,
                codigo_ofim=codigo_ofim,
                nombre_contiene=nombre_contiene,
                vendedor=vendedor,
                solo_con_micelu=solo_con_micelu,
                precio_min=precio_min,
                precio_max=precio_max,
                limit=limit,
            ),
        }
    except JsonSourceError as exc:
        return {"error": True, "mensaje": str(exc)}


async def consultar_historial_exito(
    codigo: str | None = None,
    producto_contiene: str | None = None,
    tipo_cambio: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Consulta el historial de cambios de precios/posiciones."""
    try:
        records = await load_source(_tenant(), "historial")
        return {
            "error": False,
            "fuente": "historial",
            **query_historial(
                records,
                codigo=codigo,
                producto_contiene=producto_contiene,
                tipo_cambio=tipo_cambio,
                desde=desde,
                hasta=hasta,
                limit=limit,
            ),
        }
    except JsonSourceError as exc:
        return {"error": True, "mensaje": str(exc)}


async def resumen_precios_exito() -> dict[str, Any]:
    """Resumen agregado de productos, Micelu y brechas de precio."""
    try:
        records = await load_source(_tenant(), "precios")
        return {"error": False, "fuente": "precios", **summary_precios(records)}
    except JsonSourceError as exc:
        return {"error": True, "mensaje": str(exc)}


async def resumen_historial_exito() -> dict[str, Any]:
    """Resumen agregado del historial de cambios."""
    try:
        records = await load_source(_tenant(), "historial")
        return {"error": False, "fuente": "historial", **summary_historial(records)}
    except JsonSourceError as exc:
        return {"error": True, "mensaje": str(exc)}

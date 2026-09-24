"""
Herramienta `consultar_sheet`: consulta datos de Google Sheets del cliente.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def consultar_sheet(
    hoja: str,
    filtros: dict | None = None,
    limite: int = 1000,
) -> dict:
    """
    Consulta datos de una hoja de Google Sheets del tenant activo.
    - `hoja`: nombre exacto de la pestaña.
    - `filtros`: opcional, dict {columna: valor} para filtrar (case-insensitive).
    - `limite`: máximo de filas (default 1000, techo 5000).
    """
    from mind.tenants.context import get_tenant
    from mind.data.sheets.google_sheets import (
        read_sheet,
        ExternalSheetsError,
        MAX_ROWS,
    )

    tenant = get_tenant()
    conf = getattr(tenant, "external_sheets", None)
    if not conf:
        return {
            "error": True,
            "mensaje": "No hay Google Sheets configurado.",
        }

    # Validar limite
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        return {"error": True, "mensaje": "El parámetro 'limite' debe ser un número entero."}
    if limite < 1:
        return {"error": True, "mensaje": "El parámetro 'limite' debe ser mayor o igual a 1."}
    limite = min(limite, MAX_ROWS)

    # Validar filtros
    if filtros is not None and not isinstance(filtros, dict):
        return {"error": True, "mensaje": "El parámetro 'filtros' debe ser un diccionario {columna: valor}."}

    try:
        rows = await read_sheet(conf, hoja, filters=filtros, limit=limite)
        columns = list(rows[0].keys()) if rows else []
        return {
            "error": False,
            "data": rows,
            "columns": columns,
            "sheet": hoja,
            "row_count": len(rows),
        }
    except ExternalSheetsError as exc:
        return {"error": True, "mensaje": str(exc)}
    except Exception as exc:
        logger.warning("Error en consultar_sheet tenant=%s: %s", tenant.slug, exc)
        return {"error": True, "mensaje": str(exc)}
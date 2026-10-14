"""
Herramienta `consultar_excel`: consulta datos de un archivo Excel en
OneDrive/SharePoint del cliente.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


async def consultar_excel(
    hoja: str,
    filtros: dict | None = None,
    limite: int = 1000,
) -> dict:
    """
    Consulta datos de una hoja del Excel en OneDrive/SharePoint del tenant activo.
    - `hoja`: nombre exacto de la pestaña.
    - `filtros`: opcional, dict {columna: valor} para filtrar (case-insensitive).
    - `limite`: máximo de filas (default 1000, techo 5000).
    """
    from mind.tenants.context import get_tenant
    from mind.data.excel.excel_connector import (
        read_sheet,
        ExternalExcelError,
        MAX_ROWS,
    )

    tenant = get_tenant()
    conf = getattr(tenant, "external_excel", None)
    logger.info(
        "consultar_excel tenant=%s hoja=%s filtros=%s limite=%s conf_keys=%s",
        tenant.slug, hoja, filtros, limite,
        list(conf.keys()) if conf else "NO CONF",
    )
    if not conf:
        return {"error": True, "mensaje": "No hay Excel configurado (OneDrive/SharePoint)."}

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
        logger.info(
            "consultar_excel tenant=%s hoja=%s ok filas=%s",
            tenant.slug, hoja, len(rows),
        )
        return {
            "error": False,
            "data": rows,
            "columns": columns,
            "sheet": hoja,
            "row_count": len(rows),
        }
    except ExternalExcelError as exc:
        logger.warning(
            "consultar_excel tenant=%s hoja=%s ExternalExcelError: %s",
            tenant.slug, hoja, exc,
        )
        return {"error": True, "mensaje": str(exc)}
    except Exception as exc:
        logger.warning(
            "consultar_excel tenant=%s hoja=%s Exception: %s",
            tenant.slug, hoja, exc,
        )
        return {"error": True, "mensaje": str(exc)}
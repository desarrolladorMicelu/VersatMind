"""
Herramienta `ejecutar_consulta`: consultas SQL SELECT a la base de datos
externa del cliente vía el conector de solo lectura.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def ejecutar_consulta(sql: str) -> dict:
    """
    Ejecuta una consulta SELECT genérica en la base de datos externa
    del tenant activo y retorna los resultados (máx. 200 filas).
    """
    from mind.tenants.context import get_tenant
    from mind.data.external.postgresql import execute_query

    tenant = get_tenant()
    logger.info("SQL ejecutada tenant=%s: %.400s", tenant.slug, sql)
    if not getattr(tenant, "external_db", None):
        return {
            "error": True,
            "mensaje": "No hay base de datos externa configurada.",
        }
    try:
        results = await execute_query(tenant, sql)
        return {
            "error": False,
            "data": results,
            "row_count": len(results),
        }
    except Exception as exc:
        logger.warning("Error en ejecutar_consulta tenant=%s: %s", tenant.slug, exc)
        return {"error": True, "mensaje": str(exc)}
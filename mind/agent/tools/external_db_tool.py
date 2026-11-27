"""
Herramienta `ejecutar_consulta`: consultas SQL SELECT a la base de datos
externa del cliente vía el conector de solo lectura.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def ejecutar_consulta(sql: str, base: str = "principal") -> dict:
    """
    Ejecuta una consulta SELECT genérica en la base de datos externa
    del tenant activo y retorna los resultados (máx. 200 filas).
    """
    from mind.tenants.context import get_tenant
    from mind.data.external.postgresql import execute_query

    tenant = get_tenant()
    logger.info("SQL ejecutada tenant=%s base=%s: %.400s", tenant.slug, base, sql)
    alias = (base or "principal").strip().lower()
    creds = getattr(tenant, "external_db", None) if alias in ("", "principal") else None
    if alias not in ("", "principal"):
        from sqlalchemy import select
        import mind.db.base as db
        from mind.db.models import TenantDatabase
        if db._session_factory is None:
            return {"error": True, "mensaje": "Base de datos no disponible."}
        async with db._session_factory() as session:
            row = (await session.execute(
                select(TenantDatabase).where(
                    TenantDatabase.tenant_id == tenant.id,
                    TenantDatabase.alias == alias,
                    TenantDatabase.is_active.is_(True),
                )
            )).scalar_one_or_none()
            creds = row.config if row is not None else None
    if not creds:
        return {
            "error": True,
            "mensaje": f"No hay base de datos externa configurada con alias {alias!r}.",
        }
    try:
        results = await execute_query(tenant, sql, creds)
        return {
            "error": False,
            "data": results,
            "row_count": len(results),
        }
    except Exception as exc:
        logger.warning("Error en ejecutar_consulta tenant=%s: %s", tenant.slug, exc)
        return {"error": True, "mensaje": str(exc)}
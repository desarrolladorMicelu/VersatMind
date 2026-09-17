"""
Resolución y carga de tenants desde la base de datos.

- resolve_tenant_by_token: busca el tenant por bot_token (usado en webhook)
- resolve_tenant_by_id: busca por id (usado en admin y scheduler)
- load_all_active_tenants: carga todos los tenants activos al startup
- get_token_tenant_map: diccionario token→tenant para lookup O(1)
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.db.models import Tenant

logger = logging.getLogger(__name__)

# Cache en memoria: token → Tenant  (se recarga en cada startup y con TTL)
_token_map: dict[str, Tenant] = {}
_id_map: dict[int, Tenant] = {}


def _populate_cache(tenants: list[Tenant]) -> None:
    _token_map.clear()
    _id_map.clear()
    for t in tenants:
        _token_map[t.bot_token] = t
        _id_map[t.id] = t


async def load_all_active_tenants(session: AsyncSession) -> list[Tenant]:
    """
    Carga todos los tenants activos y los almacena en caché.
    Llamar desde el lifespan de FastAPI.
    """
    result = await session.execute(
        select(Tenant).where(Tenant.is_active.is_(True))
    )
    tenants = list(result.scalars().all())
    _populate_cache(tenants)
    logger.info("Tenants activos cargados: %s", [t.slug for t in tenants])
    return tenants


async def reload_tenant(tenant_id: int, session: AsyncSession) -> Tenant | None:
    """Recarga un tenant específico en caché (tras editar desde el panel admin)."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant:
        _token_map[tenant.bot_token] = tenant
        _id_map[tenant.id] = tenant
    return tenant


def resolve_by_token(bot_token: str) -> Tenant | None:
    """Retorna el tenant correspondiente al token del bot. O(1)."""
    return _token_map.get(bot_token)


def resolve_by_id(tenant_id: int) -> Tenant | None:
    """Retorna el tenant por id. O(1)."""
    return _id_map.get(tenant_id)


def get_all_cached() -> list[Tenant]:
    """Retorna todos los tenants en caché."""
    return list(_id_map.values())

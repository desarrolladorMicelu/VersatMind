"""
Sistema de autorización de Mind by Versat.
Verifica whitelist (tabla users) y permisos por rol.
Cache LRU de 60 s para propagar cambios sin redespliegue.
Requisitos: 2.1, 2.4, 2.5, 2.6, 2.7, 2.8
"""
from __future__ import annotations

import asyncio
import time as _time
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.db.models import Role, RolePermission, User


class Permission(str, Enum):
    """Permisos disponibles en el sistema."""
    READ_SALES = "READ_SALES"
    READ_KPI = "READ_KPI"
    READ_FINANCE = "READ_FINANCE"
    GENERATE_REPORT = "GENERATE_REPORT"
    MANAGE_TASKS = "MANAGE_TASKS"


@dataclass
class AuthResult:
    """Resultado de la verificación de acceso."""
    allowed: bool
    user: User | None = None
    role: Role | None = None


class WhitelistUnavailableError(Exception):
    """La whitelist no está disponible (timeout o DB caída)."""
    pass


# --- Cache de permisos por rol (TTL 60 s) ---
_permissions_cache: dict[int, tuple[frozenset[str], float]] = {}
_CACHE_TTL_SECONDS = 60


def _get_cached_permissions(role_id: int) -> frozenset[str] | None:
    entry = _permissions_cache.get(role_id)
    if entry is None:
        return None
    permissions, cached_at = entry
    if _time.monotonic() - cached_at > _CACHE_TTL_SECONDS:
        del _permissions_cache[role_id]
        return None
    return permissions


def _set_cached_permissions(role_id: int, permissions: frozenset[str]) -> None:
    _permissions_cache[role_id] = (permissions, _time.monotonic())


def _invalidate_permissions_cache() -> None:
    """Limpia la caché. Útil en tests."""
    _permissions_cache.clear()


async def check_access(
    chat_id: int,
    session: AsyncSession,
    timeout_seconds: float = 5.0,
) -> AuthResult:
    """
    Verifica que el chat_id esté en la whitelist y activo.
    Timeout de 5 s — lanza WhitelistUnavailableError si se agota.
    Requisitos: 2.1, 2.4, 2.7, 2.8
    """
    try:
        async with asyncio.timeout(timeout_seconds):
            stmt = select(User).where(
                User.chat_id == chat_id,
                User.is_active.is_(True),
            )
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if user is None:
                return AuthResult(allowed=False)

            role_stmt = select(Role).where(Role.id == user.role_id)
            role_result = await session.execute(role_stmt)
            role = role_result.scalar_one_or_none()

            return AuthResult(allowed=True, user=user, role=role)

    except asyncio.TimeoutError as exc:
        raise WhitelistUnavailableError(
            f"Timeout al consultar whitelist para chat_id={chat_id}"
        ) from exc
    except Exception as exc:
        raise WhitelistUnavailableError(
            f"Error al consultar whitelist: {type(exc).__name__}"
        ) from exc


async def has_permission(
    role: Role,
    tool_name: str,
    session: AsyncSession,
) -> bool:
    """
    Verifica si el rol puede ejecutar la herramienta.
    Usa cache de 60 s. Requisitos: 2.5, 2.6
    """
    cached = _get_cached_permissions(role.id)
    if cached is not None:
        return tool_name in cached

    stmt = select(RolePermission.permission_name).where(
        RolePermission.role_id == role.id
    )
    result = await session.execute(stmt)
    permission_names = frozenset(row[0] for row in result.fetchall())
    _set_cached_permissions(role.id, permission_names)
    return tool_name in permission_names


def is_authorized(chat_id: int, whitelist: frozenset[int]) -> bool:
    """
    Versión pura (sin DB) para property-based testing.
    Propiedad 4 — Valida: Requisito 2.1
    """
    return chat_id in whitelist

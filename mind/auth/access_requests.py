"""
Gestión de solicitudes de acceso para Mind by Versat.
Flujo: usuario solicita → admin aprueba/rechaza con botones Telegram.
Scoped por tenant_id.
"""
from __future__ import annotations

import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mind.db.models import AccessRequest, Role, RolePermission, User

logger = logging.getLogger(__name__)

ALL_PERMISSIONS = ["READ_SALES", "READ_KPI", "READ_FINANCE", "GENERATE_REPORT", "MANAGE_TASKS", "READ_EXTERNAL_DB"]


async def get_or_create_request(
    chat_id: int,
    tenant_id: int,
    user_id: int,
    username: str | None,
    first_name: str | None,
    session: AsyncSession,
) -> tuple[AccessRequest, bool]:
    """
    Retorna (request, is_new).
    Si ya existe una solicitud pendiente para este tenant+chat_id, retorna la existente.
    """
    stmt = select(AccessRequest).where(
        AccessRequest.chat_id == chat_id,
        AccessRequest.tenant_id == tenant_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return existing, False

    req = AccessRequest(
        chat_id=chat_id,
        tenant_id=tenant_id,
        user_id=user_id,
        username=username,
        first_name=first_name,
        status="pending",
    )
    session.add(req)
    await session.flush()
    return req, True


async def approve_user(chat_id: int, tenant_id: int, session: AsyncSession) -> User | None:
    """
    Aprueba una solicitud: crea el usuario con rol board_member y todos los permisos.
    Retorna el User creado, o None si no había solicitud pendiente.
    """
    stmt = select(AccessRequest).where(
        AccessRequest.chat_id == chat_id,
        AccessRequest.tenant_id == tenant_id,
        AccessRequest.status == "pending",
    )
    result = await session.execute(stmt)
    req = result.scalar_one_or_none()
    if req is None:
        return None

    # Obtener o crear rol board_member para este tenant
    role_stmt = select(Role).where(
        Role.name == "board_member",
        Role.tenant_id == tenant_id,
    )
    role_result = await session.execute(role_stmt)
    role = role_result.scalar_one_or_none()

    if role is None:
        role = Role(name="board_member", description="Miembro de junta directiva", tenant_id=tenant_id)
        session.add(role)
        await session.flush()
        for perm in ALL_PERMISSIONS:
            session.add(RolePermission(role_id=role.id, permission_name=perm))
        await session.flush()
    else:
        perm_stmt = select(RolePermission).where(RolePermission.role_id == role.id)
        perm_result = await session.execute(perm_stmt)
        existing_perms = {p.permission_name for p in perm_result.scalars().all()}
        for perm in ALL_PERMISSIONS:
            if perm not in existing_perms:
                session.add(RolePermission(role_id=role.id, permission_name=perm))
        await session.flush()

    user = User(
        chat_id=req.chat_id,
        tenant_id=tenant_id,
        user_id=req.user_id,
        username=req.username,
        role_id=role.id,
        is_active=True,
    )
    session.add(user)

    await session.execute(
        update(AccessRequest)
        .where(
            AccessRequest.chat_id == chat_id,
            AccessRequest.tenant_id == tenant_id,
        )
        .values(status="approved")
    )
    await session.flush()
    return user


async def reject_request(chat_id: int, tenant_id: int, session: AsyncSession) -> bool:
    """Marca la solicitud como rechazada. Retorna True si existía."""
    result = await session.execute(
        update(AccessRequest)
        .where(
            AccessRequest.chat_id == chat_id,
            AccessRequest.tenant_id == tenant_id,
            AccessRequest.status == "pending",
        )
        .values(status="rejected")
    )
    return result.rowcount > 0

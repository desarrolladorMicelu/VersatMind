"""Identidad y tenant efectivo para el chat web (admin o usuario portal)."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import get_effective_tenant_id
from mind.auth.authorization import Permission
from mind.auth.data_policy import (
    SourcePolicy,
    empty_policy,
    load_permissions_for_roles,
    load_source_policy,
)
from mind.auth.portal import resolve_membership
from mind.db.models import PortalUser, Role


@dataclass(frozen=True)
class ChatIdentity:
    tenant_id: int
    owner: str
    role_ids: frozenset[int]
    permissions: frozenset[str]
    policy: SourcePolicy


async def resolve_chat_identity(
    session: AsyncSession,
    auth: dict,
    requested_tenant_id: int | None,
) -> ChatIdentity:
    role = auth.get("role")

    if role in ("superadmin", "tenant_admin"):
        tid = get_effective_tenant_id(auth, requested_tenant_id)
        if role == "superadmin":
            return ChatIdentity(
                tenant_id=tid,
                owner=str(auth.get("sub") or "admin"),
                role_ids=frozenset(),
                permissions=frozenset(p.value for p in Permission),
                policy=empty_policy(),
            )
        admin_role = (await session.execute(
            select(Role).where(Role.tenant_id == tid, Role.name == "admin").limit(1)
        )).scalar_one_or_none()
        if admin_role is None:
            return ChatIdentity(
                tenant_id=tid,
                owner=str(auth.get("sub") or "admin"),
                role_ids=frozenset(),
                permissions=frozenset(p.value for p in Permission),
                policy=empty_policy(),
            )
        permissions = await load_permissions_for_roles(session, {admin_role.id})
        policy = await load_source_policy(session, {admin_role.id}, tid)
        return ChatIdentity(
            tenant_id=tid,
            owner=str(auth.get("sub") or "admin"),
            role_ids=frozenset({admin_role.id}),
            permissions=permissions,
            policy=policy,
        )

    if role == "portal_user":
        portal_user_id = int(auth.get("portal_user_id") or 0)
        if not portal_user_id:
            raise HTTPException(status_code=401, detail="Token sin usuario de portal")
        portal = await session.get(PortalUser, portal_user_id)
        if portal is None or not portal.is_active:
            raise HTTPException(status_code=401, detail="Cuenta desactivada")
        if requested_tenant_id is None:
            raise HTTPException(status_code=422, detail="tenant_id requerido")
        row = await resolve_membership(session, portal_user_id, int(requested_tenant_id))
        if row is None:
            raise HTTPException(status_code=403, detail="No tienes acceso a esa tienda")
        membership, _tenant, role_obj = row
        permissions = await load_permissions_for_roles(session, {role_obj.id})
        policy = await load_source_policy(session, {role_obj.id}, int(requested_tenant_id))
        return ChatIdentity(
            tenant_id=int(requested_tenant_id),
            owner=f"portal:{portal_user_id}",
            role_ids=frozenset({role_obj.id}),
            permissions=permissions,
            policy=policy,
        )

    raise HTTPException(status_code=403, detail="Acceso no permitido")

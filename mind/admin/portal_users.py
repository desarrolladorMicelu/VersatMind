"""Gestión de usuarios de portal y sus pertenencias multi-tienda."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import require_admin, require_superadmin
from mind.auth.portal import (
    PortalUserError,
    create_portal_user,
    reveal_temp_password,
    set_portal_password,
    set_portal_temp_password,
    sync_memberships,
    sync_telegram_link,
    unlink_telegram,
)
from mind.db.base import get_session
from mind.db.models import Membership, PortalUser, Role, Tenant, User

router = APIRouter(prefix="/api/admin/portal-users", tags=["portal-users"])


class MembershipIn(BaseModel):
    tenant_id: int
    role_id: int


class PortalUserCreate(BaseModel):
    username: str
    password: str | None = None
    generate_temp_password: bool = True
    full_name: str | None = None
    memberships: list[MembershipIn]
    telegram_chat_id: int | None = None


class PortalUserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    password: str | None = None


class MembershipsUpdate(BaseModel):
    memberships: list[MembershipIn]


class TelegramLinkUpdate(BaseModel):
    chat_id: int | None = None


def _tenant_scope(auth: dict) -> int | None:
    return None if auth.get("role") == "superadmin" else int(auth.get("tenant_id"))


async def _load_portal(session: AsyncSession, portal_id: int) -> PortalUser:
    portal = await session.get(PortalUser, portal_id)
    if portal is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return portal


async def _ensure_manage(session: AsyncSession, auth: dict, portal_id: int) -> None:
    scope = _tenant_scope(auth)
    if scope is None:
        return
    exists = (await session.execute(
        select(Membership.id).where(
            Membership.portal_user_id == portal_id,
            Membership.tenant_id == scope,
        ).limit(1)
    )).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


async def _has_other_memberships(session: AsyncSession, portal_id: int, scope: int) -> bool:
    return bool((await session.execute(
        select(Membership.id).where(
            Membership.portal_user_id == portal_id,
            Membership.tenant_id != scope,
        ).limit(1)
    )).first())


def _portal_dict(portal: PortalUser, memberships, telegram_rows) -> dict:
    return {
        "id": portal.id,
        "username": portal.username,
        "full_name": portal.full_name,
        "is_active": portal.is_active,
        "must_change_password": portal.must_change_password,
        "has_temp_password": bool(portal.temp_password_enc),
        "has_password": bool(portal.password_hash),
        "created_at": portal.created_at.isoformat() if portal.created_at else None,
        "memberships": [
            {
                "id": m.id,
                "tenant_id": m.tenant_id,
                "tenant_name": t.name,
                "tenant_slug": t.slug,
                "role_id": m.role_id,
                "role_name": r.name,
                "role_description": r.description,
                "is_active": m.is_active,
            }
            for m, t, r in memberships
        ],
        "telegram_links": [
            {"chat_id": u.chat_id, "tenant_id": u.tenant_id}
            for u in telegram_rows
        ],
    }


@router.get("")
async def list_portal_users(
    auth=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    scope = _tenant_scope(auth)
    stmt = select(PortalUser)
    if scope is not None:
        stmt = stmt.join(Membership, Membership.portal_user_id == PortalUser.id).where(
            Membership.tenant_id == scope
        ).distinct()
    elif tenant_id is not None:
        stmt = stmt.join(Membership, Membership.portal_user_id == PortalUser.id).where(
            Membership.tenant_id == tenant_id
        ).distinct()
    portals = (await session.execute(stmt.order_by(PortalUser.username.asc()))).scalars().all()

    result = []
    for portal in portals:
        m_stmt = (
            select(Membership, Tenant, Role)
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .join(Role, Role.id == Membership.role_id)
            .where(Membership.portal_user_id == portal.id)
            .order_by(Tenant.name.asc())
        )
        if scope is not None:
            m_stmt = m_stmt.where(Membership.tenant_id == scope)
        memberships = (await session.execute(m_stmt)).all()
        t_stmt = select(User).where(User.portal_user_id == portal.id)
        if scope is not None:
            t_stmt = t_stmt.where(User.tenant_id == scope)
        telegram_rows = (await session.execute(t_stmt)).scalars().all()
        entry = _portal_dict(portal, memberships, telegram_rows)
        if scope is not None:
            entry["store_active"] = all(m.is_active for m, _t, _r in memberships) if memberships else False
        result.append(entry)
    return result


@router.post("")
async def create_portal(
    body: PortalUserCreate,
    auth=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    scope = _tenant_scope(auth)
    memberships = [m.model_dump() for m in body.memberships]
    if scope is not None:
        if any(int(m["tenant_id"]) != scope for m in memberships):
            raise HTTPException(status_code=403, detail="Solo puedes asignar tu propia tienda")
    if not memberships:
        raise HTTPException(status_code=422, detail="Selecciona al menos una tienda")

    if not body.password and not body.generate_temp_password:
        raise HTTPException(status_code=422, detail="Define una contraseña o genera una temporal")
    if scope is not None and body.telegram_chat_id is not None:
        raise HTTPException(status_code=403, detail="Solo el superadmin puede vincular Telegram")

    try:
        portal, temp = await create_portal_user(
            session,
            username=body.username,
            password=body.password,
            full_name=body.full_name,
            generate_temp=not body.password and body.generate_temp_password,
        )
        saved = await sync_memberships(session, portal, memberships)
        if body.telegram_chat_id is not None:
            await sync_telegram_link(
                session, portal, body.telegram_chat_id, saved,
            )
        await session.commit()
        await session.refresh(portal)
    except PortalUserError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "id": portal.id,
        "username": portal.username,
        "temp_password": temp,
    }


@router.patch("/{portal_id}")
async def update_portal(
    portal_id: int,
    body: PortalUserUpdate,
    auth=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_manage(session, auth, portal_id)
    portal = await _load_portal(session, portal_id)
    scope = _tenant_scope(auth)
    if scope is not None and body.password and await _has_other_memberships(session, portal_id, scope):
        raise HTTPException(
            status_code=403,
            detail="Solo el superadmin puede cambiar la contraseña de un usuario multi-tienda",
        )
    if scope is not None and body.is_active is not None:
        membership = (await session.execute(
            select(Membership).where(
                Membership.portal_user_id == portal_id,
                Membership.tenant_id == scope,
            )
        )).scalar_one_or_none()
        if membership is not None:
            membership.is_active = body.is_active
        await session.commit()
        return {"ok": True}
    if body.full_name is not None:
        portal.full_name = body.full_name.strip() or None
    if body.is_active is not None:
        portal.is_active = body.is_active
    if body.password:
        await set_portal_password(session, portal, body.password)
    await session.commit()
    return {"ok": True}


@router.put("/{portal_id}/memberships")
async def update_memberships(
    portal_id: int,
    body: MembershipsUpdate,
    auth=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_manage(session, auth, portal_id)
    portal = await _load_portal(session, portal_id)
    scope = _tenant_scope(auth)

    current = (await session.execute(
        select(Membership).where(Membership.portal_user_id == portal.id)
    )).scalars().all()
    if scope is None:
        desired = [m.model_dump() for m in body.memberships]
    else:
        desired = [
            {"tenant_id": m.tenant_id, "role_id": m.role_id}
            for m in current if m.tenant_id != scope
        ]
        desired.extend([
            m.model_dump() for m in body.memberships
            if int(m.tenant_id) == scope
        ])
    if not desired and scope is None:
        raise HTTPException(status_code=422, detail="El usuario necesita al menos una tienda")

    try:
        saved = await sync_memberships(session, portal, desired)
        telegram = (await session.execute(
            select(User).where(User.portal_user_id == portal.id).limit(1)
        )).scalar_one_or_none()
        if telegram is not None:
            await sync_telegram_link(session, portal, telegram.chat_id, saved)
        await session.commit()
    except PortalUserError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


@router.post("/{portal_id}/temp-password")
async def generate_temp_password_endpoint(
    portal_id: int,
    auth=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_manage(session, auth, portal_id)
    portal = await _load_portal(session, portal_id)
    scope = _tenant_scope(auth)
    if scope is not None and await _has_other_memberships(session, portal_id, scope):
        raise HTTPException(
            status_code=403,
            detail="Solo el superadmin puede generar contraseña a un usuario multi-tienda",
        )
    plain = await set_portal_temp_password(session, portal)
    await session.commit()
    return {"temp_password": plain}


@router.get("/{portal_id}/temp-password")
async def get_temp_password(
    portal_id: int,
    auth=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_manage(session, auth, portal_id)
    portal = await _load_portal(session, portal_id)
    scope = _tenant_scope(auth)
    if scope is not None and await _has_other_memberships(session, portal_id, scope):
        raise HTTPException(
            status_code=403,
            detail="Solo el superadmin puede ver la contraseña de un usuario multi-tienda",
        )
    plain = reveal_temp_password(portal)
    if not plain:
        raise HTTPException(status_code=404, detail="No hay contraseña temporal disponible")
    return {"temp_password": plain}


@router.put("/{portal_id}/telegram")
async def update_telegram_link(
    portal_id: int,
    body: TelegramLinkUpdate,
    auth=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    portal = await _load_portal(session, portal_id)
    try:
        if body.chat_id is None:
            await unlink_telegram(session, portal)
        else:
            memberships = (await session.execute(
                select(Membership).where(Membership.portal_user_id == portal.id)
            )).scalars().all()
            await sync_telegram_link(session, portal, body.chat_id, memberships)
        await session.commit()
    except PortalUserError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


@router.delete("/{portal_id}")
async def delete_portal(
    portal_id: int,
    auth=Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
):
    portal = await _load_portal(session, portal_id)
    await session.delete(portal)
    await session.commit()
    return {"ok": True}

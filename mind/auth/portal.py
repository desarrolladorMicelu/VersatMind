"""Cuentas de portal y pertenencias multi-tienda."""
from __future__ import annotations

import base64
import hashlib
import re
import secrets

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import hash_password
from mind.config import settings
from mind.db.models import (
    Membership,
    PortalUser,
    Role,
    SuperAdmin,
    Tenant,
    TenantAdmin,
    User,
    UserRole,
)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


class PortalUserError(ValueError):
    pass


def _fernet() -> Fernet:
    secret = (settings.ADMIN_SECRET_KEY or "mind-portal").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def generate_temp_password() -> str:
    return "Mind-" + secrets.token_urlsafe(9)


def _store_temp_password(portal: PortalUser, password: str) -> None:
    portal.password_hash = hash_password(password)
    portal.temp_password_enc = _fernet().encrypt(password.encode("utf-8")).decode("ascii")
    portal.must_change_password = True


def reveal_temp_password(portal: PortalUser) -> str | None:
    if not portal.temp_password_enc:
        return None
    try:
        return _fernet().decrypt(portal.temp_password_enc.encode("ascii")).decode("utf-8")
    except Exception:
        return None


def clear_temp_after_login(portal: PortalUser) -> None:
    portal.temp_password_enc = None


async def _username_reserved(session: AsyncSession, username: str) -> bool:
    if username == settings.ADMIN_USER:
        return True
    if (await session.execute(
        select(TenantAdmin.id).where(TenantAdmin.username == username).limit(1)
    )).first():
        return True
    if (await session.execute(
        select(SuperAdmin.id).where(SuperAdmin.username == username).limit(1)
    )).first():
        return True
    if (await session.execute(
        select(PortalUser.id).where(PortalUser.username == username).limit(1)
    )).first():
        return True
    return False


async def create_portal_user(
    session: AsyncSession,
    *,
    username: str,
    password: str | None = None,
    full_name: str | None = None,
    generate_temp: bool = False,
) -> tuple[PortalUser, str | None]:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise PortalUserError("Usuario inválido: usa 3-64 caracteres (letras, números, punto, guion o guion bajo)")
    if await _username_reserved(session, username):
        raise PortalUserError("Ese usuario ya está en uso")

    plain_temp: str | None = None
    portal = PortalUser(
        username=username,
        full_name=(full_name or "").strip() or None,
        is_active=True,
    )
    if password:
        portal.password_hash = hash_password(password)
    elif generate_temp or not password:
        plain_temp = generate_temp_password()
        _store_temp_password(portal, plain_temp)

    session.add(portal)
    await session.flush()
    return portal, plain_temp


async def set_portal_temp_password(session: AsyncSession, portal: PortalUser) -> str:
    plain = generate_temp_password()
    _store_temp_password(portal, plain)
    await session.flush()
    return plain


async def set_portal_password(session: AsyncSession, portal: PortalUser, password: str) -> None:
    portal.password_hash = hash_password(password)
    portal.temp_password_enc = None
    portal.must_change_password = False
    await session.flush()


async def resolve_memberships(
    session: AsyncSession, portal_user_id: int, include_inactive: bool = False,
):
    stmt = (
        select(Membership, Tenant, Role)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.portal_user_id == portal_user_id)
        .order_by(Tenant.name.asc())
    )
    if not include_inactive:
        stmt = stmt.where(Membership.is_active.is_(True), Tenant.is_active.is_(True))
    return (await session.execute(stmt)).all()


async def resolve_membership(
    session: AsyncSession, portal_user_id: int, tenant_id: int,
):
    row = (await session.execute(
        select(Membership, Tenant, Role)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .join(Role, Role.id == Membership.role_id)
        .where(
            Membership.portal_user_id == portal_user_id,
            Membership.tenant_id == tenant_id,
            Membership.is_active.is_(True),
            Tenant.is_active.is_(True),
        )
    )).first()
    return row


async def load_portal_access(
    session: AsyncSession, portal_user_id: int, tenant_id: int,
) -> tuple[int, frozenset[str], object] | None:
    from mind.auth.data_policy import load_permissions_for_roles, load_source_policy

    row = await resolve_membership(session, portal_user_id, tenant_id)
    if row is None:
        return None
    membership, _tenant, role = row
    permissions = await load_permissions_for_roles(session, {role.id})
    policy = await load_source_policy(session, {role.id}, tenant_id)
    return role.id, permissions, policy


async def sync_memberships(
    session: AsyncSession,
    portal: PortalUser,
    memberships: list[dict],
) -> list[Membership]:
    """
    Reemplaza las pertenencias del portal. `memberships` = [{tenant_id, role_id}].
    Valida que cada rol pertenezca a su tienda.
    """
    normalized: dict[int, int] = {}
    for item in memberships:
        tenant_id = int(item.get("tenant_id"))
        role_id = int(item.get("role_id"))
        normalized[tenant_id] = role_id
    for tenant_id, role_id in normalized.items():
        role = (await session.execute(
            select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if role is None:
            raise PortalUserError("El rol no pertenece a la tienda seleccionada")

    current = (await session.execute(
        select(Membership).where(Membership.portal_user_id == portal.id)
    )).scalars().all()
    by_tenant = {m.tenant_id: m for m in current}
    for tenant_id, role_id in normalized.items():
        membership = by_tenant.pop(tenant_id, None)
        if membership is None:
            membership = Membership(
                portal_user_id=portal.id, tenant_id=tenant_id,
                role_id=role_id, is_active=True,
            )
            session.add(membership)
        else:
            membership.role_id = role_id
            membership.is_active = True
    for membership in by_tenant.values():
        await session.delete(membership)
    await session.flush()
    return list((await session.execute(
        select(Membership).where(Membership.portal_user_id == portal.id)
    )).scalars().all())


async def sync_telegram_link(
    session: AsyncSession,
    portal: PortalUser,
    chat_id: int,
    memberships: list[Membership],
    *,
    telegram_user_id: int | None = None,
) -> None:
    """Crea/actualiza las filas `users` del chat de Telegram para las tiendas."""
    other = (await session.execute(
        select(User).where(
            User.chat_id == chat_id,
            User.portal_user_id.is_not(None),
            User.portal_user_id != portal.id,
        ).limit(1)
    )).first()
    if other:
        raise PortalUserError("Ese chat de Telegram ya está vinculado a otro usuario")

    desired = {m.tenant_id: m.role_id for m in memberships}
    existing = (await session.execute(
        select(User).where(User.portal_user_id == portal.id)
    )).scalars().all()
    by_tenant = {u.tenant_id: u for u in existing}

    for tenant_id, role_id in desired.items():
        user = by_tenant.pop(tenant_id, None)
        if user is None:
            user = User(
                chat_id=chat_id,
                tenant_id=tenant_id,
                user_id=telegram_user_id or chat_id,
                username=portal.full_name or portal.username,
                role_id=role_id,
                is_active=True,
                portal_user_id=portal.id,
            )
            session.add(user)
        else:
            user.chat_id = chat_id
            user.role_id = role_id
            user.portal_user_id = portal.id
            user.is_active = True
            user.is_paused = False
        if (await session.execute(
            select(UserRole).where(
                UserRole.tenant_id == tenant_id,
                UserRole.chat_id == chat_id,
                UserRole.role_id == role_id,
            )
        )).first() is None:
            session.add(UserRole(tenant_id=tenant_id, chat_id=chat_id, role_id=role_id))

    for user in by_tenant.values():
        await session.delete(user)
    await session.flush()


async def unlink_telegram(session: AsyncSession, portal: PortalUser) -> None:
    rows = (await session.execute(
        select(User).where(User.portal_user_id == portal.id)
    )).scalars().all()
    for row in rows:
        await session.delete(row)
    await session.flush()


async def backfill_portal_users(session: AsyncSession) -> int:
    """
    Crea PortalUser + Membership para usuarios de Telegram existentes.
    Idempotente; genera contraseña temporal cifrada para cada cuenta nueva.
    """
    rows = (await session.execute(
        select(User).where(User.portal_user_id.is_(None)).order_by(User.chat_id.asc())
    )).scalars().all()
    created = 0
    by_chat: dict[int, list[User]] = {}
    for user in rows:
        by_chat.setdefault(int(user.chat_id), []).append(user)

    for chat_id, users in by_chat.items():
        base = f"tg_{abs(chat_id)}"
        username = base
        suffix = 1
        existing = (await session.execute(
            select(PortalUser).where(PortalUser.username == username)
        )).scalar_one_or_none()
        while existing is not None and any(u.portal_user_id != existing.id for u in users):
            suffix += 1
            username = f"{base}_{suffix}"[:64]
            existing = (await session.execute(
                select(PortalUser).where(PortalUser.username == username)
            )).scalar_one_or_none()

        if existing is None:
            attempt = 0
            while True:
                try:
                    existing, _temp = await create_portal_user(
                        session,
                        username=username,
                        full_name=users[0].username or username,
                        generate_temp=True,
                    )
                    break
                except PortalUserError:
                    attempt += 1
                    username = f"{base}_{attempt}"[:64]
            created += 1
        portal = existing

        for user in users:
            user.portal_user_id = portal.id
            role = (await session.execute(
                select(Role).where(Role.id == user.role_id, Role.tenant_id == user.tenant_id)
            )).scalar_one_or_none()
            if role is not None:
                membership = (await session.execute(
                    select(Membership).where(
                        Membership.portal_user_id == portal.id,
                        Membership.tenant_id == user.tenant_id,
                    )
                )).scalar_one_or_none()
                if membership is None:
                    session.add(Membership(
                        portal_user_id=portal.id, tenant_id=user.tenant_id,
                        role_id=role.id, is_active=True,
                    ))
        await session.flush()
    return created

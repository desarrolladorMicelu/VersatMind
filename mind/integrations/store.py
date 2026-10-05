"""
Persistencia y ciclo de vida de las conexiones OAuth (tokens cifrados,
renovación automática). Una conexión activa por tenant + proveedor.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.integrations.crypto import decrypt, encrypt
from mind.integrations.oauth import OAuthError, refresh_access_token
from mind.integrations.providers import get_provider

logger = logging.getLogger(__name__)

_REFRESH_MARGIN = timedelta(seconds=120)


class IntegrationError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _apply_token_data(conn, token_data: dict) -> None:
    access = token_data.get("access_token") or ""
    refresh = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")
    conn.access_token_encrypted = encrypt(access)
    if refresh:
        conn.refresh_token_encrypted = encrypt(refresh)
    if expires_in:
        try:
            conn.token_expires_at = _now() + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            conn.token_expires_at = None
    scope = token_data.get("scope") or token_data.get("scopes")
    if scope:
        conn.scopes = scope if isinstance(scope, str) else " ".join(scope)
    conn.status = "connected"
    conn.last_error = None


async def list_connections(session: AsyncSession, tenant_id: int) -> list:
    from mind.db.models import IntegrationConnection
    return (await session.execute(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.tenant_id == tenant_id,
            IntegrationConnection.is_active.is_(True),
        )
        .order_by(IntegrationConnection.provider, IntegrationConnection.account_email)
    )).scalars().all()


async def get_connection_by_id(session: AsyncSession, tenant_id: int, conn_id: int):
    from mind.db.models import IntegrationConnection
    return (await session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.id == conn_id,
            IntegrationConnection.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()


async def get_active_connection(
    session: AsyncSession, tenant_id: int, provider: str, account_email: str | None = None
):
    from mind.db.models import IntegrationConnection
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.tenant_id == tenant_id,
        IntegrationConnection.provider == provider,
        IntegrationConnection.is_active.is_(True),
    )
    if account_email:
        stmt = stmt.where(IntegrationConnection.account_email == account_email)
    return (await session.execute(stmt.limit(1))).scalar_one_or_none()


async def get_active_providers(session: AsyncSession, tenant_id: int) -> set[str]:
    from mind.db.models import IntegrationConnection
    rows = (await session.execute(
        select(IntegrationConnection.provider).where(
            IntegrationConnection.tenant_id == tenant_id,
            IntegrationConnection.is_active.is_(True),
            IntegrationConnection.status == "connected",
        )
    )).scalars().all()
    return set(rows)


async def save_connection(
    session: AsyncSession,
    *,
    tenant_id: int,
    provider: str,
    owner: str,
    account_email: str,
    external_account_id: str | None,
    token_data: dict,
) -> "object":
    from mind.db.models import IntegrationConnection

    # Desactivar conexiones previas del mismo proveedor (una activa por proveedor)
    for other in await list_connections(session, tenant_id):
        if other.provider == provider and other.account_email != account_email:
            other.is_active = False

    conn = (await session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.tenant_id == tenant_id,
            IntegrationConnection.provider == provider,
            IntegrationConnection.account_email == account_email,
        )
    )).scalar_one_or_none()
    if conn is None:
        conn = IntegrationConnection(
            tenant_id=tenant_id,
            provider=provider,
            owner=owner,
            account_email=account_email,
            external_account_id=external_account_id,
        )
        session.add(conn)

    conn.owner = owner
    conn.external_account_id = external_account_id or conn.external_account_id
    conn.is_active = True
    _apply_token_data(conn, token_data)
    await session.commit()
    await session.refresh(conn)
    return conn


async def get_valid_access_token(session: AsyncSession, conn) -> str:
    """Devuelve un access token válido, renovándolo si está por expirar."""
    now = _now()
    token = decrypt(conn.access_token_encrypted)
    if token and conn.token_expires_at and conn.token_expires_at - now > _REFRESH_MARGIN:
        return token

    refresh = decrypt(conn.refresh_token_encrypted)
    provider = get_provider(conn.provider)
    if not refresh or provider is None:
        if token:
            return token
        raise IntegrationError("La conexión no tiene token válido; vuelve a vincular la cuenta.")

    try:
        data = await refresh_access_token(provider, refresh)
    except OAuthError as exc:
        conn.status = "error"
        conn.last_error = str(exc)[:500]
        await session.commit()
        raise IntegrationError(f"No se pudo renovar el token de {provider.label}: {exc}") from exc

    _apply_token_data(conn, data)
    await session.commit()
    return decrypt(conn.access_token_encrypted)


async def mark_error(session: AsyncSession, conn, message: str) -> None:
    conn.status = "error"
    conn.last_error = (message or "")[:500]
    await session.commit()


async def disconnect(session: AsyncSession, conn) -> None:
    conn.is_active = False
    conn.status = "revoked"
    conn.access_token_encrypted = ""
    conn.refresh_token_encrypted = None
    await session.commit()

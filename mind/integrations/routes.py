"""
Rutas HTTP para vincular y gestionar cuentas de Outlook / Google.

- El panel (autenticado) pide la URL de autorización y abre el consentimiento.
- El proveedor redirige al callback (sin cookie de sesión), que validamos con
  el `state` firmado y guardamos la conexión con tokens cifrados.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import get_effective_tenant_id, require_admin
from mind.db.base import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/integrations", tags=["integrations"])


def _base_url() -> str:
    from mind.config import settings
    return (settings.INTEGRATIONS_BASE_URL or settings.TELEGRAM_WEBHOOK_URL or "").rstrip("/")


def _serialize(conn) -> dict:
    return {
        "id": conn.id,
        "provider": conn.provider,
        "account_email": conn.account_email,
        "status": conn.status,
        "scopes": conn.scopes,
        "last_error": conn.last_error,
        "created_at": conn.created_at.isoformat() if conn.created_at else None,
        "updated_at": conn.updated_at.isoformat() if conn.updated_at else None,
    }


@router.get("/providers")
async def providers_status(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.integrations.providers import is_configured, list_providers
    from mind.integrations.store import list_connections

    tid = get_effective_tenant_id(admin, tenant_id)
    conns = {c.provider: c for c in await list_connections(session, tid)}
    out = []
    for p in list_providers():
        conn = conns.get(p.key)
        out.append({
            "provider": p.key,
            "label": p.label,
            "configured": is_configured(p.key),
            "connected": bool(conn),
            "account_email": conn.account_email if conn else None,
            "status": conn.status if conn else None,
            "connection_id": conn.id if conn else None,
            "last_error": conn.last_error if conn else None,
        })
    return out


@router.get("/connections")
async def connections_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.integrations.store import list_connections
    tid = get_effective_tenant_id(admin, tenant_id)
    return [_serialize(c) for c in await list_connections(session, tid)]


@router.get("/{provider}/start")
async def start_oauth(
    provider: str,
    admin=Depends(require_admin),
    tenant_id: int | None = Query(default=None),
):
    from mind.integrations.oauth import OAuthError, build_authorize_url
    from mind.integrations.providers import get_provider, is_configured
    from mind.integrations.state import make_state

    tid = get_effective_tenant_id(admin, tenant_id)
    cfg = get_provider(provider)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Proveedor no soportado")
    if not is_configured(cfg.key):
        raise HTTPException(
            status_code=422,
            detail=f"El proveedor {cfg.label} no está configurado en el servidor "
                   "(faltan client id/secret).",
        )
    state = make_state(tid, cfg.key, str(admin.get("sub") or "admin"))
    try:
        return {"authorize_url": build_authorize_url(cfg, state), "provider": cfg.key}
    except OAuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    """Callback del proveedor (sin cookie de sesión; se valida el `state`)."""
    from mind.db.base import _session_factory
    from mind.integrations.oauth import OAuthError, exchange_code, fetch_account_email
    from mind.integrations.providers import get_provider
    from mind.integrations.state import read_state
    from mind.integrations.store import save_connection

    base = _base_url()

    def _redirect(status: str, provider_key: str, msg: str = "") -> RedirectResponse:
        url = f"{base}/admin/integraciones?integration={status}&provider={provider_key}"
        if msg:
            url += f"&message={quote(msg[:180])}"
        return RedirectResponse(url, status_code=302)

    if error:
        return _redirect("error", provider, f"El proveedor devolvió: {error}")
    if not code or not state:
        return _redirect("error", provider, "Faltan parámetros code/state.")

    data = read_state(state)
    if data is None:
        return _redirect("error", provider, "Estado OAuth inválido o expirado.")

    if data.get("p") != (provider or "").lower():
        return _redirect("error", provider, "Proveedor no coincide con el estado.")

    cfg = get_provider(provider)
    if cfg is None or _session_factory is None:
        return _redirect("error", provider, "Proveedor no disponible.")

    try:
        token_data = await exchange_code(cfg, code)
        access = token_data.get("access_token", "")
        email = await fetch_account_email(cfg, access)
        async with _session_factory() as session:
            await save_connection(
                session,
                tenant_id=int(data["tid"]),
                provider=cfg.key,
                owner=str(data.get("o") or ""),
                account_email=email or "cuenta",
                external_account_id=None,
                token_data=token_data,
            )
        logger.info("Integración %s vinculada para tenant %s (%s)", cfg.key, data["tid"], email)
        return _redirect("ok", cfg.key, email)
    except OAuthError as exc:
        logger.warning("OAuth %s falló: %s", provider, exc)
        return _redirect("error", cfg.key, str(exc))
    except Exception as exc:
        logger.error("Error en callback OAuth %s: %s", provider, exc)
        return _redirect("error", cfg.key, "No se pudo completar la vinculación.")


@router.post("/connections/{connection_id}/test")
async def connection_test(
    connection_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.integrations.mail import list_recent
    from mind.integrations.store import get_connection_by_id
    tid = get_effective_tenant_id(admin, tenant_id)
    conn = await get_connection_by_id(session, tid, connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    try:
        msgs = await list_recent(session, conn, limit=1)
        return {"ok": True, "correos": len(msgs)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


@router.delete("/connections/{connection_id}")
async def connection_delete(
    connection_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = Query(default=None),
):
    from mind.integrations.store import disconnect, get_connection_by_id
    tid = get_effective_tenant_id(admin, tenant_id)
    conn = await get_connection_by_id(session, tid, connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    await disconnect(session, conn)
    return {"ok": True}

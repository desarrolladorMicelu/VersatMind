"""
Flujo OAuth 2.0 (authorization code) para Outlook y Google.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from mind.integrations.providers import (
    ProviderConfig,
    client_credentials,
)

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    pass


def _base_url() -> str:
    from mind.config import settings
    return (settings.INTEGRATIONS_BASE_URL or settings.TELEGRAM_WEBHOOK_URL or "").rstrip("/")


def redirect_uri(provider: str) -> str:
    return f"{_base_url()}/api/admin/integrations/{provider}/callback"


def build_authorize_url(provider: ProviderConfig, state: str) -> str:
    client_id, _ = client_credentials(provider.key)
    if not client_id:
        raise OAuthError(f"Falta configurar las credenciales OAuth de {provider.label}.")
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri(provider.key),
        "scope": " ".join(provider.scopes),
        "state": state,
    }
    params.update(provider.extra_authorize_params)
    return f"{provider.authorize_url}?{urlencode(params)}"


async def _token_request(provider: ProviderConfig, data: dict) -> dict:
    client_id, client_secret = client_credentials(provider.key)
    if not client_id or not client_secret:
        raise OAuthError(f"Falta configurar las credenciales OAuth de {provider.label}.")
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        **data,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            provider.token_url,
            data=payload,
            headers={"Accept": "application/json"},
        )
    if resp.status_code >= 400:
        raise OAuthError(f"{provider.label}: {resp.status_code} {resp.text[:300]}")
    return resp.json()


async def exchange_code(provider: ProviderConfig, code: str) -> dict:
    return await _token_request(provider, {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(provider.key),
    })


async def refresh_access_token(provider: ProviderConfig, refresh_token: str) -> dict:
    return await _token_request(provider, {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(provider.scopes),
    })


async def fetch_account_email(provider: ProviderConfig, access_token: str) -> str:
    """Obtiene el email de la cuenta usando el endpoint de perfil."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            provider.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code >= 400:
        raise OAuthError(f"No se pudo leer el perfil de {provider.label}: {resp.status_code}")
    data = resp.json()
    # Graph: mail / userPrincipalName · Google: email
    return data.get("mail") or data.get("userPrincipalName") or data.get("email") or ""

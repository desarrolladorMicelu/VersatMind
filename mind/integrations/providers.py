"""
Registro de proveedores OAuth soportados (Outlook / Google).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderConfig:
    key: str
    label: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    userinfo_url: str
    extra_authorize_params: dict[str, str] = field(default_factory=dict)


def _outlook() -> ProviderConfig:
    from mind.config import settings
    tenant = (settings.MS_TENANT_ID or "common").strip() or "common"
    return ProviderConfig(
        key="outlook",
        label="Outlook (Microsoft 365)",
        authorize_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        token_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        scopes=(
            "offline_access",
            "User.Read",
            "Mail.Read",
            "Mail.ReadWrite",
            "Calendars.Read",
        ),
        userinfo_url="https://graph.microsoft.com/v1.0/me",
    )


def _google() -> ProviderConfig:
    return ProviderConfig(
        key="google",
        label="Google (Gmail / Calendar)",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=(
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/calendar.readonly",
        ),
        userinfo_url="https://www.googleapis.com/oauth2/v3/userinfo",
        extra_authorize_params={"access_type": "offline", "prompt": "consent"},
    )


_PROVIDERS = {"outlook": _outlook, "google": _google}


def get_provider(key: str) -> ProviderConfig | None:
    factory = _PROVIDERS.get((key or "").lower())
    return factory() if factory else None


def list_providers() -> list[ProviderConfig]:
    return [f() for f in _PROVIDERS.values()]


def client_credentials(key: str) -> tuple[str, str]:
    from mind.config import settings
    key = (key or "").lower()
    if key == "outlook":
        return settings.MS_CLIENT_ID, settings.MS_CLIENT_SECRET
    if key == "google":
        return settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET
    return "", ""


def is_configured(key: str) -> bool:
    cid, secret = client_credentials(key)
    return bool(cid and secret)

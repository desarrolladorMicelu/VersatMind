"""
`state` firmado para el flujo OAuth (anti-CSRF y binding de tenant).

El callback de OAuth llega sin cookie de sesión, así que validamos que el
`state` fue emitido por nosotros, no expiró y contiene el tenant/proveedor.
"""
from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_SALT = "mind-integrations-oauth-state"
MAX_AGE_SECONDS = 900  # 15 minutos


def _serializer() -> URLSafeTimedSerializer:
    from mind.config import settings
    return URLSafeTimedSerializer(settings.ADMIN_SECRET_KEY, salt=_SALT)


def make_state(tenant_id: int, provider: str, owner: str) -> str:
    return _serializer().dumps({"tid": tenant_id, "p": provider, "o": owner})


def read_state(token: str, max_age: int = MAX_AGE_SECONDS) -> dict | None:
    try:
        return _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    except Exception:
        return None

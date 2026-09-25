"""
Autenticación del panel de administración — JWT en cookie httpOnly.

Roles:
  - superadmin: credenciales del .env (ADMIN_USER/ADMIN_PASSWORD).
                Puede ver y gestionar TODOS los tenants.
                JWT incluye role="superadmin", tenant_id=None.

  - tenant_admin: credenciales en tabla tenant_admins.
                  Solo puede ver y gestionar SU tenant.
                  JWT incluye role="tenant_admin", tenant_id=<id>.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
from fastapi import HTTPException, Request
from jose import JWTError, jwt

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


def _secret() -> str:
    from mind.config import settings
    return settings.ADMIN_SECRET_KEY


# ── Creación de tokens ────────────────────────────────────────────────────────

def create_access_token(
    username: str,
    role: Literal["superadmin", "tenant_admin"] = "superadmin",
    tenant_id: int | None = None,
) -> str:
    payload: dict = {
        "sub": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except JWTError:
        return None


# ── Hashing de contraseñas ───────────────────────────────────────────────────

_BCRYPT_MAX_BYTES = 72


def _bcrypt_secret(password: str) -> bytes:
    # bcrypt solo considera los primeros 72 bytes y desde 4.1 rechaza más
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_secret(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_secret(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


# ── Verificación de credenciales ─────────────────────────────────────────────

def verify_superadmin(username: str, password: str) -> bool:
    from mind.config import settings
    return username == settings.ADMIN_USER and password == settings.ADMIN_PASSWORD


# Alias legacy para no romper código existente
def verify_credentials(username: str, password: str) -> bool:
    return verify_superadmin(username, password)


# ── Dependencia FastAPI ───────────────────────────────────────────────────────

def require_admin(request: Request) -> dict:
    """
    Extrae el JWT de cookie o header Authorization.
    Retorna el payload completo: {sub, role, tenant_id?, exp}
    """
    token = request.cookies.get("admin_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return payload


def require_superadmin(request: Request) -> dict:
    """Dependencia que solo permite superadmin."""
    payload = require_admin(request)
    if payload.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Requiere rol superadmin")
    return payload


def get_effective_tenant_id(payload: dict, tenant_id_param: int | None) -> int:
    """
    Resuelve el tenant_id efectivo según el rol del admin:
    - superadmin: usa el tenant_id que pase como parámetro (requerido)
    - tenant_admin: ignora el parámetro y usa su propio tenant_id del JWT
    """
    role = payload.get("role", "superadmin")
    if role == "superadmin":
        if tenant_id_param is None:
            raise HTTPException(status_code=422, detail="tenant_id requerido para superadmin")
        return tenant_id_param
    # tenant_admin
    tid = payload.get("tenant_id")
    if tid is None:
        raise HTTPException(status_code=401, detail="Token sin tenant_id")
    return int(tid)

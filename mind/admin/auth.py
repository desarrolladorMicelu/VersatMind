"""
Autenticación del panel de administración — JWT en cookie httpOnly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException, Request, status
from jose import JWTError, jwt

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


def _secret() -> str:
    from mind.config import settings
    return settings.ADMIN_SECRET_KEY


def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except JWTError:
        return None


def verify_credentials(username: str, password: str) -> bool:
    from mind.config import settings
    return username == settings.ADMIN_USER and password == settings.ADMIN_PASSWORD


def require_admin(request: Request) -> dict:
    """Dependencia FastAPI: extrae JWT de cookie o header Authorization."""
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

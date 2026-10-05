"""
Cifrado de tokens de integración (Fernet).

La clave se toma de INTEGRATIONS_ENCRYPTION_KEY; si no está configurada, se
deriva de forma determinística de ADMIN_SECRET_KEY (suficiente para cifrar en
reposo; se recomienda definir la clave explícita en producción).
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    from mind.config import settings

    key = (settings.INTEGRATIONS_ENCRYPTION_KEY or "").strip()
    if not key:
        digest = hashlib.sha256(settings.ADMIN_SECRET_KEY.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest).decode("ascii")
    return Fernet(key.encode("ascii"))


def encrypt(plain: str | None) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(blob: str | None) -> str:
    if not blob:
        return ""
    try:
        return _fernet().decrypt(blob.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        logger.warning("No se pudo descifrar un token de integración: %s", type(exc).__name__)
        return ""

"""
Sistema de auditoría de Mind by Versat.
Registra interacciones, accesos no autorizados y fallos en PostgreSQL.
Nunca almacena secretos.
Requisitos: 8.1-8.7, 9.6
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import insert

MAX_REQUEST_CHARS = 4_000
MAX_RESPONSE_CHARS = 4_000
MAX_TOOL_RESULT_CHARS = 4_000
MAX_ERROR_CHARS = 2_000

_SENSITIVE_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_PASS")
_TOKEN_PREFIXES = re.compile(r"(Bearer\s+|sk-|xoxb-|xoxp-)([A-Za-z0-9_\-]{20,})")


def _build_secret_values() -> frozenset[str]:
    secrets: set[str] = set()
    for key, value in os.environ.items():
        if any(key.upper().endswith(s) for s in _SENSITIVE_SUFFIXES):
            if value and len(value) >= 4:
                secrets.add(value)
    return frozenset(secrets)


_SECRET_VALUES: frozenset[str] = _build_secret_values()


def sanitize(text: str) -> str:
    """
    Reemplaza por [REDACTED] todos los valores sensibles.
    Idempotente: sanitize(sanitize(x)) == sanitize(x).
    Propiedad 20 — Valida: Requisitos 8.5, 8.6
    """
    result = text
    for secret in _SECRET_VALUES:
        result = result.replace(secret, "[REDACTED]")
    result = _TOKEN_PREFIXES.sub(r"\1[REDACTED]", result)
    return result


def _truncate(text: str | None, max_chars: int) -> str | None:
    if text is None:
        return None
    return text[:max_chars] if len(text) > max_chars else text


@dataclass
class AuditRecord:
    """Entrada del registro de auditoría."""
    event_type: str  # 'interaction' | 'unauthorized' | 'tool_failure' | 'scheduler'
    chat_id: int | None = None
    user_id: int | None = None
    tenant_id: int | None = None
    request_content: str | None = None
    tool_invoked: str | None = None
    tool_params: dict | None = None
    tool_result: str | None = None
    response_content: str | None = None
    status: str | None = None  # 'success' | 'error'
    error_description: str | None = None
    timestamp_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    def __post_init__(self) -> None:
        if self.request_content:
            self.request_content = _truncate(sanitize(self.request_content), MAX_REQUEST_CHARS)
        if self.response_content:
            self.response_content = _truncate(sanitize(self.response_content), MAX_RESPONSE_CHARS)
        if self.tool_result:
            self.tool_result = _truncate(sanitize(self.tool_result), MAX_TOOL_RESULT_CHARS)
        if self.error_description:
            self.error_description = _truncate(sanitize(self.error_description), MAX_ERROR_CHARS)
        if self.tool_params:
            self.tool_params = {
                k: sanitize(str(v)) if isinstance(v, str) else v
                for k, v in self.tool_params.items()
            }


async def _write_record(record: AuditRecord) -> None:
    """Persiste un registro. Importa dependencias de forma lazy para evitar ciclos."""
    from mind.db.base import _session_factory
    from mind.db.models import AuditLog

    if _session_factory is None:
        raise RuntimeError("session_factory no disponible")

    async with _session_factory() as session:
        stmt = insert(AuditLog).values(
            event_type=record.event_type,
            timestamp_utc=record.timestamp_utc,
            chat_id=record.chat_id,
            user_id=record.user_id,
            tenant_id=record.tenant_id,
            request_content=record.request_content,
            tool_invoked=record.tool_invoked,
            tool_params=record.tool_params,
            tool_result=record.tool_result,
            response_content=record.response_content,
            status=record.status,
            error_description=record.error_description,
        )
        await session.execute(stmt)
        await session.commit()


def _write_to_stderr(error_description: str, event_type: str) -> None:
    timestamp = datetime.utcnow().isoformat()
    print(
        f"[AUDIT_FAIL] timestamp={timestamp} event_type={event_type!r} "
        f"error={error_description!r}",
        file=sys.stderr,
        flush=True,
    )


async def log_interaction(record: AuditRecord) -> None:
    """
    Persiste con reintentos (3 intentos, 2 s entre cada uno).
    Si todos fallan escribe en stderr y no lanza excepción.
    Requisitos: 8.1, 8.2, 8.7
    """
    last_error: str = ""
    for attempt in range(3):
        try:
            await _write_record(record)
            return
        except Exception as exc:
            last_error = str(exc)
            if attempt < 2:
                await asyncio.sleep(2)
    _write_to_stderr(last_error, record.event_type)


async def log_unauthorized(chat_id: int, user_id: int | None, content: str, tenant_id: int | None = None) -> None:
    """Registra un intento de acceso no autorizado."""
    record = AuditRecord(
        event_type="unauthorized",
        chat_id=chat_id,
        user_id=user_id,
        tenant_id=tenant_id,
        request_content=content,
        status="error",
        error_description="Acceso no autorizado",
    )
    await log_interaction(record)


async def log_tool_failure(
    tool_name: str,
    params: dict,
    error: str,
    chat_id: int | None = None,
    tenant_id: int | None = None,
) -> None:
    """Registra el fallo de una herramienta."""
    record = AuditRecord(
        event_type="tool_failure",
        chat_id=chat_id,
        tenant_id=tenant_id,
        tool_invoked=tool_name,
        tool_params=params,
        status="error",
        error_description=error,
    )
    await log_interaction(record)

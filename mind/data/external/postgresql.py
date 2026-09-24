"""
Conector a base de datos externa PostgreSQL — solo lectura SELECT.

Valida las consultas del agente (solo SELECT, una sola sentencia),
calcula el objeto `asyncpg.Connection`, ejecuta y retorna list[dict]
con claves en minúsculas y valores JSON-serializables.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class ExternalDbError(Exception):
    """Error genérico de la base de datos externa."""


class InvalidQueryError(ExternalDbError):
    """La consulta no cumple las validaciones de seguridad (no SELECT, multi-sentencia)."""


_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_LIMIT_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Sanitización de SQL: remover literales/comentarios para analizar top-level
# ---------------------------------------------------------------------------

def _strip_literals(sql: str) -> str:
    """
    Reemplaza por espacios (preservando longitud) los fragmentos que no son
    SQL top-level: string literals '...', identifiers "..." y '$tag$...$tag$',
    comentarios de línea -- y de bloque /* */.
    """
    out = list(sql)
    n = len(sql)
    i = 0
    while i < n:
        ch = sql[i]
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            end = min(j + 1, n)
            for k in range(i, end):
                if out[k] != "\n":
                    out[k] = " "
            i = end
        elif ch == '"':
            j = i + 1
            while j < n and sql[j] != '"':
                j += 1
            end = min(j + 1, n)
            for k in range(i, end):
                if out[k] != "\n":
                    out[k] = " "
            i = end
        elif ch == "-" and i + 1 < n and sql[i + 1] == "-":
            j = sql.find("\n", i)
            if j == -1:
                for k in range(i, n):
                    out[k] = " "
                break
            for k in range(i, j):
                out[k] = " "
            i = j
        elif ch == "/" and i + 1 < n and sql[i + 1] == "*":
            j = sql.find("*/", i + 2)
            end = n if j == -1 else j + 2
            for k in range(i, end):
                if out[k] != "\n":
                    out[k] = " "
            i = end
        elif ch == "$":
            m = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$", sql[i:])
            if m:
                tag = m.group(0)
                close = sql.find(tag, i + len(tag))
                end = n if close == -1 else close + len(tag)
                for k in range(i, end):
                    if out[k] != "\n":
                        out[k] = " "
                i = end
            else:
                i += 1
        else:
            i += 1
    return "".join(out)


def _validate_and_clamp(sql: str) -> str:
    """Valida SELECT único y asegura un LIMIT 200 como techo de filas."""
    if not sql or not sql.strip():
        raise InvalidQueryError("La consulta está vacía.")
    stripped = _strip_literals(sql).strip()
    if not stripped:
        raise InvalidQueryError("La consulta está vacía.")
    if not _SELECT_RE.match(stripped):
        raise InvalidQueryError("Solo se permiten consultas SELECT.")
    # Permitir un solo ; al final (terminador SQL estándar)
    stripped_no_semi = stripped.rstrip(";").strip()
    if ";" in stripped_no_semi:
        raise InvalidQueryError("No se permiten múltiples sentencias SQL.")
    if _LIMIT_RE.search(stripped):
        return sql
    return sql + "\nLIMIT 200"


# ---------------------------------------------------------------------------
# Conversión de valores asyncpg a JSON
# ---------------------------------------------------------------------------

def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return str(value)


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

def _validate_creds(creds: dict) -> dict:
    """Valida y normaliza las credenciales external_db del tenant."""
    if not creds:
        raise ExternalDbError("No hay base de datos externa configurada para este tenant.")
    engine = str(creds.get("engine") or "postgresql").lower()
    if engine != "postgresql":
        raise ExternalDbError(f"Motor de base de datos externa no soportado: {engine!r}. Solo 'postgresql' por ahora.")
    host = creds.get("host") or ""
    database = creds.get("database") or ""
    if not host or not database:
        raise ExternalDbError("Faltan credenciales de la base externa: host y database son obligatorios.")
    try:
        port = int(creds.get("port") or 5432)
    except (TypeError, ValueError):
        port = 5432
    return {
        "host": host,
        "port": port,
        "database": database,
        "user": creds.get("user") or "",
        "password": creds.get("password") or "",
    }


async def _connect(creds: dict) -> asyncpg.Connection:
    c = _validate_creds(creds)
    return await asyncpg.connect(
        host=c["host"],
        port=c["port"],
        database=c["database"],
        user=c["user"],
        password=c["password"],
        timeout=15,
        command_timeout=25,
    )


async def test_connection(creds: dict) -> None:
    """
    Verifica conectividad ejecutando SELECT 1.
    Lanza ExternalDbError con el mensaje descriptivo si falla.
    """
    try:
        conn = await _connect(creds)
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
    except ExternalDbError:
        raise
    except asyncio.TimeoutError:
        raise ExternalDbError("Timeout al conectar a la base de datos externa.") from None
    except Exception as exc:
        raise ExternalDbError(f"Error de conexión: {type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# Ejecución de consultas
# ---------------------------------------------------------------------------

async def execute_query(tenant: Any, sql: str) -> list[dict]:
    """
    Conecta a la base externa del tenant, ejecuta un SELECT y retorna
    list[dict] con claves en minúsculas (máximo 200 filas).
    """
    creds = getattr(tenant, "external_db", None)
    final_sql = _validate_and_clamp(sql)
    try:
        conn = await _connect(creds)
        try:
            rows = await conn.fetch(final_sql)
        finally:
            await conn.close()
    except InvalidQueryError:
        raise
    except ExternalDbError:
        raise
    except asyncio.TimeoutError:
        raise ExternalDbError("Timeout ejecutando la consulta en la base de datos externa.") from None
    except asyncpg.PostgresError as exc:
        raise ExternalDbError(f"Error de PostgreSQL: {exc}") from exc
    except Exception as exc:
        raise ExternalDbError(f"Error ejecutando la consulta: {type(exc).__name__}: {exc}") from exc

    if not rows:
        return []
    return [
        {name.lower(): _to_jsonable(value) for name, value in dict(record).items()}
        for record in rows
    ]
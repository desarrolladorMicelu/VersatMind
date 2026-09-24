"""
Descubrimiento de esquema de la base de datos externa.

- `introspect_schema`: conecta y lee information_schema (tablas, columnas, PK).
- `generate_schema_description`: envía el esquema raw al LLM (OpenRouter)
  para obtener una descripción en español; si falla, formatea el raw.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import asyncpg

from mind.data.external.postgresql import (
    ExternalDbError,
    _connect,
    _validate_creds,
)

logger = logging.getLogger(__name__)


_TABLES_SQL = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ORDER BY table_name
"""

_COLUMNS_SQL = """
    SELECT table_name, column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public'
    ORDER BY table_name, ordinal_position
"""

_PKS_SQL = """
    SELECT tc.table_name, kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND tc.table_schema = 'public'
"""


async def introspect_schema(creds: dict) -> list[dict]:
    """
    Conecta a la base externa y retorna su esquema:
    [{table: str, columns: [{name, type, nullable, is_pk}]}]
    Timeout total 30 s.
    """
    try:
        conn = await _connect(creds)
        try:
            table_rows = await conn.fetch(_TABLES_SQL, timeout=25)
            tables = [r["table_name"] for r in table_rows]

            column_rows = await conn.fetch(_COLUMNS_SQL, timeout=25)
            columns_by_table: dict[str, list[dict[str, Any]]] = {}
            for r in column_rows:
                columns_by_table.setdefault(r["table_name"], []).append({
                    "name": r["column_name"],
                    "type": r["data_type"],
                    "nullable": r["is_nullable"] == "YES",
                    "is_pk": False,
                })

            pk_rows = await conn.fetch(_PKS_SQL, timeout=25)
            for r in pk_rows:
                for col in columns_by_table.get(r["table_name"], []):
                    if col["name"] == r["column_name"]:
                        col["is_pk"] = True
        finally:
            await conn.close()
    except ExternalDbError:
        raise
    except asyncio.TimeoutError:
        raise ExternalDbError("Timeout al consultar el esquema de la base de datos externa.") from None
    except asyncpg.PostgresError as exc:
        raise ExternalDbError(f"Error de PostgreSQL al leer el esquema: {exc}") from exc
    except Exception as exc:
        raise ExternalDbError(f"Error al leer el esquema: {type(exc).__name__}: {exc}") from exc

    return [
        {
            "table": table,
            "columns": columns_by_table.get(table, []),
        }
        for table in tables
    ]


def _format_raw_schema(raw: list[dict]) -> str:
    """Formatea el esquema raw como markdown crudo (fallback sin LLM)."""
    lines = ["# Esquema de la base de datos", ""]
    for item in raw:
        lines.append(f"## Tabla: {item['table']}")
        lines.append("")
        lines.append("| columna | tipo | nullable | clave primaria |")
        lines.append("|---|---|---|---|")
        for col in item.get("columns", []):
            lines.append(
                f"| {col['name']} | {col['type']} | "
                f"{'SÍ' if col['nullable'] else 'NO'} | "
                f"{'SÍ' if col['is_pk'] else 'NO'} |"
            )
        lines.append("")
    return "\n".join(lines)


async def generate_schema_description(raw: list[dict]) -> str:
    """
    Envía el esquema raw al LLM configurado y retorna una descripción en
    español. Si el LLM falla o retorna vacío, devuelve el raw formateado.
    """
    from mind.config import settings

    prompt = (
        "Eres un experto en bases de datos. A continuación tienes el esquema "
        "crudo de una base de datos relacional (PostgreSQL) de una empresa.\n\n"
        f"{raw}\n\n"
        "Genera una descripción del esquema en español que sirva como contexto "
        "para un agente de IA que ejecutará consultas SQL SELECT sobre esta "
        "base de datos. Agrupa las tablas por dominio de negocio y explica, "
        "para cada tabla, cuál es su propósito y qué significa cada columna "
        "(especialmente códigos, llaves foráneas y campos crípticos). "
        "Menciona las relaciones entre tablas cuando sea evidente. "
        "Usa formato Markdown, títulos por dominio/negocio y tablas o listas "
        "para las columnas. No inventes información: si algo no es claro, "
        "indícalo explícitamente."
    )

    try:
        from openai import AsyncOpenAI, APIError, APITimeoutError

        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=60,
        )
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        description = response.choices[0].message.content
        if description and description.strip():
            return description.strip()
        logger.warning("LLM retornó descripción vacía; usando esquema raw.")
        return _format_raw_schema(raw)
    except (APIError, APITimeoutError) as exc:
        logger.warning("Error del LLM al generar descripción del esquema: %s", type(exc).__name__)
        return _format_raw_schema(raw)
    except Exception as exc:
        logger.warning("Error inesperado generando descripción del esquema: %s", type(exc).__name__)
        return _format_raw_schema(raw)


_ = _validate_creds
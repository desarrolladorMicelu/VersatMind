"""
Descubrimiento de esquema de Google Sheets.

- `introspect_sheets`: conecta y lee primeras filas de cada pestaña para
  detectar columnas y tipos.
- `generate_sheets_description`: envía el esquema raw al LLM para obtener
  una descripción en español; si falla, formatea el raw.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def introspect_sheets(conf: dict) -> list[dict]:
    """
    Conecta al spreadsheet y retorna un listado de hojas con sus columnas
    y valores de ejemplo: [{sheet, columns: [{name, sample_value}]}].

    Ignora pestañas vacías (sin headers o sin datos).
    """
    from mind.data.sheets.google_sheets import (
        ExternalSheetsError,
        _open_spreadsheet,
    )

    try:
        import gspread
        ss = await _open_spreadsheet(conf)
        worksheets = await asyncio.to_thread(ss.worksheets)
    except ExternalSheetsError:
        raise
    except Exception as exc:
        raise ExternalSheetsError(
            f"Error al listar hojas: {type(exc).__name__}: {exc}"
        ) from exc

    result: list[dict[str, Any]] = []
    for ws in worksheets:
        sheet_name = ws.title
        try:
            vals = await asyncio.to_thread(
                lambda w=ws: w.get_all_values(
                    value_render_option=gspread.utils.ValueRenderOption.formatted
                )
            )
        except Exception as exc:
            logger.warning("No se pudo leer la hoja %r en discovery: %s", sheet_name, exc)
            continue

        if not vals or not vals[0]:
            continue

        # Saltar filas vacías iniciales
        start = 0
        while start < len(vals) and all(
            cell is None or (isinstance(cell, str) and cell.strip() == "")
            for cell in vals[start]
        ):
            start += 1

        if start >= len(vals):
            continue

        raw_headers = [str(c) if c is not None else "" for c in vals[start]]
        headers = [h for h in raw_headers if h.strip()]
        if not headers:
            continue

        # Tomar hasta 3 filas de muestra (primeras después del header)
        sample_rows = vals[start + 1: start + 4]
        columns = []
        for i, h in enumerate(headers):
            sample_values = []
            for row in sample_rows:
                if i < len(row) and row[i] is not None:
                    sample_values.append(str(row[i]))
            columns.append({
                "name": h,
                "sample_value": sample_values[0] if sample_values else "",
            })

        result.append({
            "sheet": sheet_name,
            "columns": columns,
        })

    return result


def _format_raw_sheets(raw: list[dict]) -> str:
    """Formatea el esquema raw de sheets como markdown (fallback sin LLM)."""
    lines = ["# Hojas de Google Sheets del cliente", ""]
    for item in raw:
        lines.append(f"## Hoja: {item['sheet']}")
        lines.append("")
        lines.append("| columna | valor de ejemplo |")
        lines.append("|---|---|")
        for col in item.get("columns", []):
            lines.append(f"| {col['name']} | {col['sample_value']} |")
        lines.append("")
    return "\n".join(lines)


async def generate_sheets_description(raw: list[dict]) -> str:
    """
    Envía el esquema raw de sheets al LLM y retorna una descripción en español.
    Si el LLM falla o retorna vacío, devuelve el raw formateado.
    """
    from mind.config import settings

    prompt = (
        "Eres un experto en análisis de datos. A continuación tienes las "
        "hojas de cálculo de Google Sheets de una empresa.\n\n"
        f"{raw}\n\n"
        "Genera una descripción en español que sirva como contexto para un "
        "agente de IA que consultará estas hojas. Para cada hoja explica su "
        "propósito probable y qué significa cada columna (especialmente "
        "códigos y campos crípticos). Indica qué hoja usar para qué tipo de "
        "consulta. Usa formato Markdown. No inventes información."
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
        return _format_raw_sheets(raw)
    except (APIError, APITimeoutError) as exc:
        logger.warning("Error del LLM al generar descripción de sheets: %s", type(exc).__name__)
        return _format_raw_sheets(raw)
    except Exception as exc:
        logger.warning("Error inesperado generando descripción de sheets: %s", type(exc).__name__)
        return _format_raw_sheets(raw)
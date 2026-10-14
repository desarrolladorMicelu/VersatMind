"""
Descubrimiento de esquema de archivos Excel en OneDrive/SharePoint.

- `introspect_excel`: conecta a OneDrive, descarga el Excel y lee primeras
  filas de cada hoja para detectar columnas y tipos.
- `generate_excel_description`: envía el esquema raw al LLM para obtener
  una descripción en español; si falla, formatea el raw.
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def introspect_excel(conf: dict) -> list[dict]:
    """
    Conecta a OneDrive, descarga el Excel y retorna un listado de hojas
    con sus columnas y valores de ejemplo: [{sheet, columns: [{name, sample_value}]}].

    Ignora hojas vacías (sin headers).
    """
    from mind.data.excel.excel_connector import (
        ExternalExcelError,
        download_file,
    )

    try:
        content = await download_file(conf)
    except ExternalExcelError:
        raise
    except Exception as exc:
        raise ExternalExcelError(
            f"Error al descargar el Excel para introspección: {type(exc).__name__}: {exc}"
        ) from exc

    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)

    result: list[dict[str, Any]] = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows_iter = ws.iter_rows(values_only=True)

        try:
            raw_headers = next(rows_iter)
        except StopIteration:
            continue

        headers = [str(c) if c is not None else "" for c in raw_headers]
        headers = [h for h in headers if h.strip()]
        if not headers:
            continue

        # Tomar hasta 3 filas de muestra
        sample_rows = []
        for _ in range(3):
            try:
                sample_rows.append(next(rows_iter))
            except StopIteration:
                break

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

    wb.close()
    return result


def _format_raw_excel(raw: list[dict]) -> str:
    """Formatea el esquema raw como markdown (fallback sin LLM)."""
    lines = ["# Archivo Excel del cliente (OneDrive/SharePoint)", ""]
    for item in raw:
        lines.append(f"## Hoja: {item['sheet']}")
        lines.append("")
        lines.append("| columna | valor de ejemplo |")
        lines.append("|---|---|")
        for col in item.get("columns", []):
            lines.append(f"| {col['name']} | {col['sample_value']} |")
        lines.append("")
    return "\n".join(lines)


async def generate_excel_description(raw: list[dict]) -> str:
    """
    Envía el esquema raw al LLM y retorna una descripción en español.
    Si el LLM falla o retorna vacío, devuelve el raw formateado.
    """
    from mind.config import settings

    prompt = (
        "Eres un experto en análisis de datos. A continuación tienes la "
        "estructura raw de varias hojas de un archivo Excel (OneDrive/SharePoint) "
        "de una empresa.\n\n"
        f"{raw}\n\n"
        "Genera una descripción en español que sirva como contexto para un "
        "agente de IA que consultará estas hojas usando la herramienta "
        "'consultar_excel'.\n\n"
        "Analiza cada hoja y basándote ÚNICAMENTE en los nombres y valores de "
        "ejemplo de las columnas, identifica:\n"
        "- El propósito probable de cada hoja según sus columnas.\n"
        "- Qué significa cada columna (especialmente códigos, IDs y campos "
        "crípticos). Explica los valores de ejemplo para dar contexto.\n"
        "- Para qué tipo de preguntas sirve cada hoja (productos, clientes, "
        "ventas, etc.).\n"
        "- Si hay columnas que se relacionan entre hojas (ej: un código de "
        "producto que aparece en dos hojas), indícalo.\n\n"
        "Usa formato Markdown. No inventes información: si algo no es claro "
        "por los nombres o valores, indícalo explícitamente."
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
        return _format_raw_excel(raw)
    except (APIError, APITimeoutError) as exc:
        logger.warning("Error del LLM al generar descripción de Excel: %s", type(exc).__name__)
        return _format_raw_excel(raw)
    except Exception as exc:
        logger.warning("Error inesperado generando descripción de Excel: %s", type(exc).__name__)
        return _format_raw_excel(raw)
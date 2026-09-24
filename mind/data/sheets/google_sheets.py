"""
Conector a Google Sheets — solo lectura.

gspread es síncrono, todas las operaciones de red se envuelven en
asyncio.to_thread() para no bloquear el event loop.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

MAX_ROWS = 5000


class ExternalSheetsError(Exception):
    """Error genérico de Google Sheets externo."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_spreadsheet_id(url_or_id: str) -> str:
    """
    Extrae el spreadsheet_id de una URL de Google Sheets o devuelve el ID
    directamente si es plano.
    """
    if not url_or_id or not url_or_id.strip():
        raise ExternalSheetsError("spreadsheet_url está vacío.")
    url_or_id = url_or_id.strip()

    # URL moderna: /spreadsheets/d/<id>/edit
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)

    # Formato con key= (URLs antiguas)
    m = re.search(r"[?&]key=([a-zA-Z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)

    # Si es solo un ID plano (letras, números, guiones, guion bajo)
    if re.match(r"^[a-zA-Z0-9_-]+$", url_or_id):
        return url_or_id

    raise ExternalSheetsError(
        f"No se pudo extraer el ID del spreadsheet de: {url_or_id!r}. "
        "Usa una URL como https://docs.google.com/spreadsheets/d/ABC123/edit "
        "o el ID directamente."
    )


def _validate_conf(conf: dict) -> dict:
    """Valida la configuración del tenant para Google Sheets."""
    if not conf:
        raise ExternalSheetsError(
            "No hay Google Sheets configurado para este tenant."
        )
    sid = conf.get("spreadsheet_id") or ""
    if not sid:
        raise ExternalSheetsError(
            "Falta spreadsheet_id en la configuración de Google Sheets."
        )
    creds = conf.get("credentials")
    if not creds or not isinstance(creds, dict):
        raise ExternalSheetsError(
            "Faltan las credenciales de la service account de Google. "
            "Pega el contenido del JSON de la service account."
        )
    required = ("type", "project_id", "private_key", "client_email", "token_uri")
    missing = [k for k in required if not creds.get(k)]
    if missing:
        raise ExternalSheetsError(
            f"Credenciales de Google incompletas. Faltan: {', '.join(missing)}. "
            "Asegúrate de pegar el JSON completo de la service account."
        )
    if creds.get("type") != "service_account":
        raise ExternalSheetsError(
            f"Tipo de credencial inválido: {creds.get('type')!r}. "
            "Debe ser 'service_account'."
        )
    return conf


def _client(conf: dict) -> Any:
    """Crea el cliente gspread síncrono desde la configuración."""
    import gspread
    creds = conf["credentials"]
    return gspread.service_account_from_dict(creds)


# ---------------------------------------------------------------------------
# Conversión a JSON
# ---------------------------------------------------------------------------

def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Operaciones de red (envueltas en to_thread)
# ---------------------------------------------------------------------------

async def _open_spreadsheet(conf: dict) -> Any:
    """Abre el spreadsheet por ID (gspread síncrono envuelto en to_thread)."""
    import gspread
    gc = _client(conf)
    sid = conf["spreadsheet_id"]
    try:
        return await asyncio.to_thread(gc.open_by_key, sid)
    except gspread.exceptions.SpreadsheetNotFound:
        raise ExternalSheetsError(
            f"Hoja de cálculo con ID {sid!r} no encontrada. "
            "Verifica que el ID sea correcto y que la hoja esté compartida "
            "con el client_email de la service account."
        ) from None
    except gspread.exceptions.APIError as exc:
        msg = str(exc)
        if "403" in msg or "PERMISSION_DENIED" in msg:
            client_email = (conf.get("credentials") or {}).get("client_email", "")
            raise ExternalSheetsError(
                f"Permiso denegado al acceder al spreadsheet. "
                f"Comparte la hoja con: {client_email}"
            ) from exc
        raise ExternalSheetsError(f"Error de API de Google Sheets: {exc}") from exc


async def _get_worksheet(spreadsheet: Any, sheet_name: str) -> Any:
    """Obtiene una worksheet por nombre (envuelto en to_thread)."""
    try:
        return await asyncio.to_thread(spreadsheet.worksheet, sheet_name)
    except Exception:
        # gspread lanza WorksheetNotFound que no es pública en v6
        available = await asyncio.to_thread(spreadsheet.worksheets)
        names = [ws.title for ws in available]
        raise ExternalSheetsError(
            f"Hoja '{sheet_name}' no encontrada. "
            f"Pestañas disponibles: {', '.join(names)}"
        ) from None


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

async def test_connection(conf: dict) -> list[str]:
    """
    Abre el spreadsheet y retorna los nombres de las pestañas.
    Lanza ExternalSheetsError si falla.
    """
    try:
        ss = await _open_spreadsheet(conf)
        worksheets = await asyncio.to_thread(ss.worksheets)
        return [ws.title for ws in worksheets]
    except ExternalSheetsError:
        raise
    except asyncio.TimeoutError:
        raise ExternalSheetsError(
            "Timeout al conectar a Google Sheets (15 s)."
        ) from None
    except Exception as exc:
        raise ExternalSheetsError(
            f"Error de conexión a Google Sheets: {type(exc).__name__}: {exc}"
        ) from exc


async def list_sheets(conf: dict) -> list[str]:
    """
    Retorna los nombres de las pestañas del spreadsheet.
    """
    return await test_connection(conf)


async def read_sheet(
    conf: dict,
    sheet_name: str,
    filters: dict[str, str] | None = None,
    limit: int = 1000,
) -> list[dict]:
    """
    Lee los datos de una hoja y retorna list[dict] con headers como claves.

    - Filters case-insensitive (str() de ambos lados).
    - Cap a MAX_ROWS (5000).
    """
    if not sheet_name or not sheet_name.strip():
        raise ExternalSheetsError("El nombre de hoja está vacío.")

    limit = max(1, min(limit, MAX_ROWS))

    try:
        import gspread
        ss = await _open_spreadsheet(conf)
        ws = await _get_worksheet(ss, sheet_name)

        # Leer todos los valores (ValueRenderOption.unformatted para números crudos)
        vals = await asyncio.to_thread(
            lambda: ws.get_all_values(value_render_option=gspread.utils.ValueRenderOption.unformatted)
        )

        if not vals or not vals[0]:
            return []

        # Saltar filas vacías iniciales
        start = 0
        while start < len(vals) and all(
            cell is None or (isinstance(cell, str) and cell.strip() == "")
            for cell in vals[start]
        ):
            start += 1

        if start >= len(vals):
            return []

        # Primera fila = headers
        raw_headers = [str(c) if c is not None else "" for c in vals[start]]
        headers: list[str] = []
        seen: dict[str, int] = {}
        for h in raw_headers:
            if not h.strip():
                h = "_"
            if h in seen:
                seen[h] += 1
                h = f"{h}_{seen[h]}"
            else:
                seen[h] = 0
            headers.append(h)

        # Filas de datos
        rows_raw = vals[start + 1:]
        result: list[dict[str, Any]] = []
        for row in rows_raw:
            # Saltar filas completamente vacías
            if all(
                cell is None or (isinstance(cell, str) and cell.strip() == "")
                for cell in row
            ):
                continue
            padded = row + [None] * (len(headers) - len(row))
            row_dict = {}
            for i, h in enumerate(headers):
                row_dict[h] = _to_jsonable(padded[i]) if padded[i] is not None else None
            result.append(row_dict)

        # Aplicar filtros en memoria (case-insensitive)
        if filters:
            valid_cols = set(headers)
            for col, val in filters.items():
                if col not in valid_cols:
                    raise ExternalSheetsError(
                        f"La columna '{col}' no existe en la hoja '{sheet_name}'. "
                        f"Columnas disponibles: {', '.join(headers)}"
                    )
            val_str = str(val).casefold()
            result = [
                r for r in result
                if str(r.get(col, "") or "").casefold() == val_str
            ]

        # Cap
        result = result[:limit]

        return result

    except ExternalSheetsError:
        raise
    except asyncio.TimeoutError:
        raise ExternalSheetsError(
            "Timeout al leer la hoja de Google Sheets (25 s)."
        ) from None
    except Exception as exc:
        raise ExternalSheetsError(
            f"Error al leer la hoja '{sheet_name}': {type(exc).__name__}: {exc}"
        ) from exc
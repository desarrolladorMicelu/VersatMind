"""
Conector a Microsoft OneDrive/SharePoint para leer archivos Excel.

OAuth2 con Microsoft Graph API para acceder a archivos .xlsx del tenant.
openpyxl lee el archivo descargado en memoria.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time as _time
import uuid
from typing import Any
from urllib.parse import urlencode

import base64

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.x509 import load_pem_x509_certificate, load_der_x509_certificate

logger = logging.getLogger(__name__)

MAX_ROWS = 5000
AUTHORIZE_URL = "https://login.microsoftonline.com/{domain}/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

DEFAULT_DOMAIN = "common"
SCOPES = [
    "openid",
    "profile",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Files.Read",
    "offline_access",
]


class ExternalExcelError(Exception):
    """Error genérico de Excel externo (OneDrive/SharePoint)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=15.0),
        follow_redirects=True,
    )


def _read_private_key(path_or_key: str) -> str:
    """
    Lee la clave privada RSA.
    - Si es una ruta de archivo existente, la lee del disco.
    - Caso contrario, asume que es el contenido PEM directamente.
    """
    import os as _os
    if _os.path.isfile(path_or_key):
        try:
            with open(path_or_key, "r") as f:
                return f.read()
        except Exception as exc:
            raise ExternalExcelError(
                f"Error al leer archivo de clave {path_or_key!r}: {exc}"
            ) from None
    # No es archivo → tratarlo como el PEM directo
    if "-----BEGIN" in path_or_key:
        return path_or_key
    raise ExternalExcelError(
        "EXCEL_CLIENT_PRIVATE_KEY debe ser la ruta a un archivo .key existente "
        "o el contenido PEM de la clave privada (incluyendo -----BEGIN RSA PRIVATE KEY-----)."
    )


def _make_client_assertion(client_id: str) -> tuple[str, str]:
    """
    Genera un JWT client_assertion firmado con RSA o usa client_secret.
    Retorna (assertion_data, assertion_type).
    """
    from mind.config import settings
    from jwt import encode as jwt_encode

    key_path = settings.EXCEL_CLIENT_PRIVATE_KEY
    cert_path = settings.EXCEL_CLIENT_CERT_FILE
    secret = settings.EXCEL_CLIENT_SECRET

    if key_path and cert_path:
        private_key = _read_private_key(key_path)
        with open(cert_path, "rb") as f:
            raw = f.read()
        try:
            cert = load_pem_x509_certificate(raw)
        except ValueError:
            cert = load_der_x509_certificate(raw)
        thumbprint = base64.urlsafe_b64encode(
            cert.fingerprint(hashes.SHA1())
        ).rstrip(b"=").decode()
        now = int(_time.time())
        payload = {
            "aud": TOKEN_URL,
            "iss": client_id,
            "sub": client_id,
            "jti": str(uuid.uuid4()),
            "exp": now + 600,
            "iat": now,
            "nbf": now,
        }
        assertion = jwt_encode(payload, private_key, algorithm="RS256", headers={"x5t": thumbprint})
        return assertion, "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
    elif secret:
        return secret, "client_secret"
    else:
        raise ExternalExcelError(
            "Configurá EXCEL_CLIENT_PRIVATE_KEY + EXCEL_CLIENT_CERT_FILE (certificado) o "
            "EXCEL_CLIENT_SECRET (secret) en el .env."
        )


async def _get_client_creds() -> tuple[str, str]:
    from mind.config import settings
    cid = settings.EXCEL_CLIENT_ID
    redirect = settings.EXCEL_REDIRECT_URI
    if not cid or not redirect:
        raise ExternalExcelError(
            "EXCEL_CLIENT_ID y EXCEL_REDIRECT_URI deben configurarse en el .env."
        )
    return cid, redirect


# ---------------------------------------------------------------------------
# OAuth2
# ---------------------------------------------------------------------------

def get_auth_url(tenant_id: int, domain: str = DEFAULT_DOMAIN) -> str:
    """Retorna la URL de autorización de Microsoft para el tenant."""
    from mind.config import settings
    cid = settings.EXCEL_CLIENT_ID
    redirect = settings.EXCEL_REDIRECT_URI
    state = f"tenant_{tenant_id}"
    params = urlencode({
        "client_id": cid,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    })
    return f"{AUTHORIZE_URL.format(domain=domain)}?{params}"


async def exchange_code(code: str) -> dict:
    """Intercambia un authorization code por tokens."""
    cid, redirect = await _get_client_creds()
    assertion, assertion_type = _make_client_assertion(cid)
    data = {
        "client_id": cid,
        "code": code,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    }
    if assertion_type == "client_secret":
        data["client_secret"] = assertion
    else:
        data["client_assertion"] = assertion
        data["client_assertion_type"] = assertion_type

    async with _client() as c:
        resp = await c.post(
            TOKEN_URL,
            data=data,
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise ExternalExcelError(
            f"Error al intercambiar código: HTTP {resp.status_code} — {resp.text[:300]}"
        )
    data = resp.json()
    if "error" in data:
        raise ExternalExcelError(
            f"Error OAuth2: {data.get('error')} — {data.get('error_description', '')}"
        )
    return data  # {access_token, refresh_token, expires_in, ...}


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresca el access_token usando el refresh_token."""
    cid, _ = await _get_client_creds()
    assertion, assertion_type = _make_client_assertion(cid)
    data = {
        "client_id": cid,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    if assertion_type == "client_secret":
        data["client_secret"] = assertion
    else:
        data["client_assertion"] = assertion
        data["client_assertion_type"] = assertion_type

    async with _client() as c:
        resp = await c.post(
            TOKEN_URL,
            data=data,
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise ExternalExcelError(
            f"Error al refrescar token: HTTP {resp.status_code} — {resp.text[:300]}"
        )
    data = resp.json()
    if "error" in data:
        raise ExternalExcelError(
            f"Error OAuth2: {data.get('error')} — {data.get('error_description', '')}"
        )
    return data


async def ensure_token(conf: dict) -> dict:
    """
    Asegura que el access_token esté vigente; si expiró, lo refresca.

    Retorna el config actualizado (con nuevo access_token si se refrescó).
    """
    import time
    conf = dict(conf)
    expires_at = conf.get("token_expires_at", 0)
    if time.time() < expires_at - 60:
        return conf  # todavía vigente
    refresh = conf.get("refresh_token")
    if not refresh:
        raise ExternalExcelError(
            "El token de acceso expiró y no hay refresh_token disponible. "
            "Reconectá OneDrive desde el panel."
        )
    data = await refresh_access_token(refresh)
    conf["access_token"] = data["access_token"]
    if "refresh_token" in data:
        conf["refresh_token"] = data["refresh_token"]
    conf["token_expires_at"] = int(time.time()) + data.get("expires_in", 3600)
    return conf


# ---------------------------------------------------------------------------
# Graph API
# ---------------------------------------------------------------------------

async def _graph_get(conf: dict, path: str, params: dict | None = None) -> Any:
    """GET a Microsoft Graph API. Refresca token si es necesario."""
    import time
    conf = await ensure_token(conf)
    token = conf["access_token"]
    async with _client() as c:
        resp = await c.get(
            f"{GRAPH_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code == 401:
        # Token expiró — forzar refresh e intentar de nuevo
        refresh = conf.get("refresh_token")
        if not refresh:
            raise ExternalExcelError("Token expirado y sin refresh_token.")
        data = await refresh_access_token(refresh)
        conf["access_token"] = data["access_token"]
        if "refresh_token" in data:
            conf["refresh_token"] = data["refresh_token"]
        conf["token_expires_at"] = int(time.time()) + data.get("expires_in", 3600)
        token = conf["access_token"]
        async with _client() as c2:
            resp = await c2.get(
                f"{GRAPH_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
    if resp.status_code != 200:
        raise ExternalExcelError(
            f"Graph API error (HTTP {resp.status_code}): {resp.text[:300]}"
        )
    return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.content


async def _graph_download(conf: dict, path: str) -> bytes:
    """Descarga binario desde Graph API."""
    import time
    conf = await ensure_token(conf)
    token = conf["access_token"]
    async with _client() as c:
        resp = await c.get(
            f"{GRAPH_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        raise ExternalExcelError(
            f"Error descargando archivo (HTTP {resp.status_code}): {resp.text[:200]}"
        )
    return resp.content


def _graph_config(conf: dict) -> dict:
    """Retorna el config actualizado que debe persistirse (access_token refrescado)."""
    return conf


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------

def _validate_conf(conf: dict) -> dict:
    """Valida la configuración del tenant para Excel externo."""
    if not conf:
        raise ExternalExcelError(
            "No hay Excel (OneDrive/SharePoint) configurado para este tenant."
        )
    if not conf.get("access_token"):
        raise ExternalExcelError(
            "Falta access_token. Conectá OneDrive desde el panel de administración."
        )
    return conf


# ---------------------------------------------------------------------------
# Operaciones
# ---------------------------------------------------------------------------

async def list_excel_files(conf: dict) -> list[dict]:
    """
    Lista archivos .xlsx del OneDrive.

    Combina el search de Graph (búsqueda full-text) con /me/drive/recent
    para incluir archivos recién creados que aún no están indexados.
    Deduplica por ID y ordena por fecha de modificación descendente.

    Retorna [{id, name, size, webUrl, lastModified}]
    """
    from urllib.parse import quote

    seen: set[str] = set()
    items: list[dict] = []
    raw: list[dict] = []

    # 1) Search full-text
    try:
        search_q = quote(".xlsx")
        resp = await _graph_get(
            conf,
            f"/me/drive/root/search(q='{search_q}')",
            {"$top": 100, "$select": "id,name,size,webUrl,lastModifiedDateTime"},
        )
        raw.extend(resp.get("value", []))
    except ExternalExcelError as exc:
        logger.warning("Search endpoint falló: %s", exc)

    # 2) Archivos recientes (cubre archivos nuevos no indexados)
    try:
        resp = await _graph_get(
            conf,
            "/me/drive/recent",
            {"$top": 100, "$select": "id,name,size,webUrl,lastModifiedDateTime"},
        )
        raw.extend(resp.get("value", []))
    except ExternalExcelError as exc:
        logger.warning("Recent endpoint falló: %s", exc)

    # 3) Merge + dedupe + filtrar solo Excel
    for item in raw:
        name = (item.get("name") or "")
        if not name.lower().endswith((".xlsx", ".xlsm", ".xls")):
            continue
        fid = item.get("id")
        if not fid or fid in seen:
            continue
        seen.add(fid)
        items.append({
            "id": fid,
            "name": name,
            "size": item.get("size", 0),
            "webUrl": item.get("webUrl", ""),
            "lastModified": item.get("lastModifiedDateTime", ""),
        })

    # 4) Fallback: root children si no encontró nada
    if not items:
        try:
            resp = await _graph_get(
                conf,
                "/me/drive/root/children",
                {"$top": 100, "$select": "id,name,size,webUrl,lastModifiedDateTime"},
            )
            for item in resp.get("value", []):
                name = (item.get("name") or "")
                if not name.lower().endswith((".xlsx", ".xlsm", ".xls")):
                    continue
                fid = item.get("id")
                if not fid or fid in seen:
                    continue
                seen.add(fid)
                items.append({
                    "id": fid,
                    "name": name,
                    "size": item.get("size", 0),
                    "webUrl": item.get("webUrl", ""),
                    "lastModified": item.get("lastModifiedDateTime", ""),
                })
        except ExternalExcelError as exc:
            logger.warning("Root children falló: %s", exc)

    items.sort(key=lambda f: f["lastModified"], reverse=True)
    return items


async def resolve_excel_item(conf: dict, url_or_id: str) -> dict:
    """
    Resuelve un archivo por su ID o pegado una URL de OneDrive.

    Acepta:
    - "DFC0619F83263D69!s8bc6059202414f93978eb2399ca84e0e" (item ID puro)
    - "https://excel.cloud.microsoft/open/onedrive/?docId=DFC0619F83263D69!xxx&driveId=..."
    - URL de OneDrive personal / SharePoint

    Retorna {id, name, size, webUrl, lastModified}
    """
    import re
    from urllib.parse import parse_qs, unquote, urlparse

    if not url_or_id or not url_or_id.strip():
        raise ExternalExcelError("URL o ID de archivo vacío.")

    raw = url_or_id.strip()

    # Caso 1: es una URL con docId / id / itemId en query params
    sid = ""
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        qs = parse_qs(parsed.query)
        for key in ("docId", "id", "itemId", "itemid"):
            if qs.get(key):
                sid = unquote(qs[key][0])
                break
        # URL estilo onedrive.live.com/edit.aspx?resid=... en 'resid'
        if not sid and qs.get("resid"):
            sid = unquote(qs["resid"][0])
        if not sid:
            # intentar extraer ID del path: /personal/xxx/resid or .../edit?resid=
            m = re.search(r"resid=([0-9a-zA-Z!]+)", raw)
            if m:
                sid = m.group(1)
            m = re.search(r"/(items|id)/([0-9a-zA-Z!]+)", raw)
            if m:
                sid = m.group(2)
    else:
        # Caso 2: es un ID directo del drive item
        sid = raw

    if not sid:
        raise ExternalExcelError(
            f"No se pudo extraer el ID del archivo de: {url_or_id[:120]!r}"
        )

    cleaned = sid.replace("%21", "!").replace("%2F", "/").strip()
    if "!" not in cleaned and cleaned.startswith("s") is False:
        # sin prefijo de drive — asumir el drive del usuario
        cleaned = f"DFC0619F83263D69!{cleaned}"

    from urllib.parse import quote as _quote
    encoded_path = "/".join(_quote(part, safe="") for part in cleaned.split("/"))
    try:
        item = await _graph_get(conf, f"/me/drive/items/{encoded_path}")
        name = item.get("name") or ""
        return {
            "id": item.get("id", cleaned),
            "name": name,
            "size": item.get("size", 0),
            "webUrl": item.get("webUrl", ""),
            "lastModified": item.get("lastModifiedDateTime", ""),
        }
    except ExternalExcelError as exc:
        raise ExternalExcelError(
            f"Archivo no encontrado en OneDrive (ID {cleaned!r}): {exc}"
        ) from exc


async def download_file(conf: dict) -> bytes:
    """Descarga el .xlsx desde OneDrive y retorna los bytes."""
    file_id = conf.get("file_id")
    if not file_id:
        raise ExternalExcelError(
            "No hay file_id seleccionado. Seleccioná un archivo Excel "
            "desde el panel de administración."
        )
    return await _graph_download(conf, f"/me/drive/items/{file_id}/content")


async def test_connection(conf: dict) -> list[str]:
    """
    Descarga el Excel y retorna los nombres de las hojas.
    Lanza ExternalExcelError si falla.
    """
    try:
        content = await download_file(conf)
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        return wb.sheetnames
    except ExternalExcelError:
        raise
    except asyncio.TimeoutError:
        raise ExternalExcelError(
            "Timeout al conectar a OneDrive/SharePoint (15 s)."
        ) from None
    except Exception as exc:
        raise ExternalExcelError(
            f"Error al leer el Excel: {type(exc).__name__}: {exc}"
        ) from exc


async def list_sheets(conf: dict) -> list[str]:
    """Retorna los nombres de las hojas del Excel."""
    return await test_connection(conf)


async def read_sheet(
    conf: dict,
    sheet_name: str,
    filters: dict[str, str] | None = None,
    limit: int = 1000,
) -> list[dict]:
    """
    Lee los datos de una hoja del Excel y retorna list[dict].

    - Filters case-insensitive.
    - Cap a MAX_ROWS (5000).
    """
    if not sheet_name or not sheet_name.strip():
        raise ExternalExcelError("El nombre de la hoja está vacío.")

    limit = max(1, min(limit, MAX_ROWS))

    try:
        content = await download_file(conf)
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)

        if sheet_name not in wb.sheetnames:
            raise ExternalExcelError(
                f"Hoja '{sheet_name}' no encontrada. "
                f"Hojas disponibles: {', '.join(wb.sheetnames)}"
            )

        ws = wb[sheet_name]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            raw_headers = [str(c) if c is not None else "" for c in next(rows_iter)]
        except StopIteration:
            wb.close()
            return []
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

        result: list[dict[str, Any]] = []
        for row in rows_iter:
            if all(c is None for c in row):
                continue
            row_dict = {}
            for i, h in enumerate(headers):
                val = row[i] if i < len(row) else None
                row_dict[h] = str(val) if val is not None else None
            result.append(row_dict)

        wb.close()

        # Filtros en memoria
        if filters:
            valid_cols = set(headers)
            for col, val in filters.items():
                if col not in valid_cols:
                    raise ExternalExcelError(
                        f"La columna '{col}' no existe en la hoja '{sheet_name}'. "
                        f"Columnas: {', '.join(headers)}"
                    )
                val_str = str(val).casefold()
                result = [
                    r for r in result
                    if str(r.get(col, "") or "").casefold() == val_str
                ]

        return result[:limit]

    except ExternalExcelError:
        raise
    except asyncio.TimeoutError:
        raise ExternalExcelError(
            "Timeout al leer la hoja de Excel (25 s)."
        ) from None
    except Exception as exc:
        raise ExternalExcelError(
            f"Error al leer la hoja '{sheet_name}': {type(exc).__name__}: {exc}"
        ) from exc
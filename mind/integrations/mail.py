"""
Lectura de correos: Outlook (Microsoft Graph) y Gmail (Google API).
Devuelve diccionarios normalizados {id, subject, from, to, date, preview, body, is_read}.
"""
from __future__ import annotations

import base64
import html
import logging
import re
from datetime import datetime, timezone

import httpx

from mind.integrations.store import IntegrationError, get_valid_access_token

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
GMAIL = "https://gmail.googleapis.com/gmail/v1"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


async def _token(session, conn) -> str:
    try:
        return await get_valid_access_token(session, conn)
    except IntegrationError:
        raise
    except Exception as exc:
        raise IntegrationError(f"No se pudo obtener token de {conn.provider}: {exc}") from exc


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30, headers={"Accept": "application/json"})


# ── Outlook / Microsoft Graph ─────────────────────────────────────────────────

def _graph_message(m: dict) -> dict:
    frm = ((m.get("from") or {}).get("emailAddress") or {})
    to = [
        ((r.get("emailAddress") or {}).get("address") or "")
        for r in (m.get("toRecipients") or [])
    ]
    body = (m.get("body") or {})
    content = body.get("content") or m.get("bodyPreview") or ""
    if body.get("contentType") == "html":
        content = _strip_html(content)
    return {
        "id": m.get("id"),
        "subject": m.get("subject") or "(sin asunto)",
        "from": frm.get("address") or "",
        "from_name": frm.get("name") or "",
        "to": [t for t in to if t],
        "date": m.get("receivedDateTime"),
        "preview": m.get("bodyPreview") or "",
        "body": content[:6000],
        "is_read": bool(m.get("isRead")),
    }


async def _graph_list(token: str, *, query: str | None, limit: int) -> list[dict]:
    select = "id,subject,from,toRecipients,receivedDateTime,bodyPreview,isRead,body"
    if query:
        params = {"$search": f'"{query}"', "$top": limit, "$select": select}
        url = f"{GRAPH}/me/messages"
    else:
        params = {"$top": limit, "$select": select, "$orderby": "receivedDateTime desc"}
        url = f"{GRAPH}/me/mailFolders/inbox/messages"
    async with _client() as client:
        resp = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        raise IntegrationError(f"Graph {resp.status_code}: {resp.text[:200]}")
    return [_graph_message(m) for m in resp.json().get("value", [])]


async def _graph_get(token: str, message_id: str) -> dict:
    params = {"$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,isRead,body"}
    async with _client() as client:
        resp = await client.get(
            f"{GRAPH}/me/messages/{message_id}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code >= 400:
        raise IntegrationError(f"Graph {resp.status_code}: {resp.text[:200]}")
    return _graph_message(resp.json())


# ── Google Gmail ──────────────────────────────────────────────────────────────

def _gmail_headers(payload: dict) -> dict:
    return {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}


def _gmail_body(payload: dict) -> str:
    """Extrae el texto plano del payload de Gmail (recursivo)."""
    mime = payload.get("mimeType", "")
    body = payload.get("body") or {}
    data = body.get("data")
    if mime == "text/plain" and data:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _gmail_body(part)
        if text:
            return text
    if data:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", "replace")
    return ""


def _gmail_message(m: dict) -> dict:
    payload = m.get("payload") or {}
    headers = _gmail_headers(payload)
    internal = m.get("internalDate")
    date = None
    if internal:
        try:
            date = datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            date = None
    return {
        "id": m.get("id"),
        "subject": headers.get("subject") or "(sin asunto)",
        "from": headers.get("from") or "",
        "from_name": "",
        "to": [t.strip() for t in (headers.get("to") or "").split(",") if t.strip()],
        "date": date,
        "preview": m.get("snippet") or "",
        "body": _gmail_body(payload)[:6000],
        "is_read": "UNREAD" not in (m.get("labelIds") or []),
    }


async def _gmail_list(token: str, *, query: str | None, limit: int) -> list[dict]:
    params = {"maxResults": limit, "labelIds": "INBOX"}
    if query:
        params["q"] = query
    async with _client() as client:
        resp = await client.get(
            f"{GMAIL}/users/me/messages",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code >= 400:
            raise IntegrationError(f"Gmail {resp.status_code}: {resp.text[:200]}")
        ids = [m["id"] for m in resp.json().get("messages", [])]
        out = []
        for mid in ids:
            r = await client.get(
                f"{GMAIL}/users/me/messages/{mid}",
                params={"format": "full"},
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code < 400:
                out.append(_gmail_message(r.json()))
        return out


async def _gmail_get(token: str, message_id: str) -> dict:
    async with _client() as client:
        resp = await client.get(
            f"{GMAIL}/users/me/messages/{message_id}",
            params={"format": "full"},
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code >= 400:
        raise IntegrationError(f"Gmail {resp.status_code}: {resp.text[:200]}")
    return _gmail_message(resp.json())


# ── API pública ───────────────────────────────────────────────────────────────

async def list_recent(session, conn, *, limit: int = 10) -> list[dict]:
    token = await _token(session, conn)
    if conn.provider == "outlook":
        return await _graph_list(token, query=None, limit=limit)
    return await _gmail_list(token, query=None, limit=limit)


async def search(session, conn, query: str, *, limit: int = 10) -> list[dict]:
    token = await _token(session, conn)
    if conn.provider == "outlook":
        return await _graph_list(token, query=query, limit=limit)
    return await _gmail_list(token, query=query, limit=limit)


async def get_message(session, conn, message_id: str) -> dict:
    token = await _token(session, conn)
    if conn.provider == "outlook":
        return await _graph_get(token, message_id)
    return await _gmail_get(token, message_id)

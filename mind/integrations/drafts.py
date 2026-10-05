"""
Creación de borradores de respuesta (sin envío).

- Outlook: se crea un mensaje borrador en /me/messages (carpeta Borradores).
- Gmail: se crea un borrador vía users.drafts.create con MIME crudo.
"""
from __future__ import annotations

import base64
import logging
from email.message import EmailMessage

import httpx

from mind.integrations.mail import get_message
from mind.integrations.store import get_valid_access_token

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
GMAIL = "https://gmail.googleapis.com/gmail/v1"


async def create_reply_draft(session, conn, message_id: str, body_text: str) -> dict:
    original = await get_message(session, conn, message_id)
    to = original.get("from") or ""
    subject = original.get("subject") or ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    token = await get_valid_access_token(session, conn)

    if conn.provider == "outlook":
        async with httpx.AsyncClient(timeout=30, headers={"Accept": "application/json"}) as client:
            resp = await client.post(
                f"{GRAPH}/me/messages",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body_text},
                    "toRecipients": [{"emailAddress": {"address": to}}] if to else [],
                },
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"Graph draft {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return {"provider": "outlook", "draft_id": data.get("id"), "to": to, "subject": subject}

    # Gmail: MIME crudo
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    async with httpx.AsyncClient(timeout=30, headers={"Accept": "application/json"}) as client:
        resp = await client.post(
            f"{GMAIL}/users/me/drafts",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"message": {"raw": raw}},
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"Gmail draft {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return {"provider": "google", "draft_id": data.get("id"), "to": to, "subject": subject}

"""
Tests de integraciones OAuth (Outlook/Google): cifrado, state y normalizadores.
"""
from __future__ import annotations

import base64
from types import SimpleNamespace

from mind.config import settings
from mind.integrations import crypto, state
from mind.integrations.calendar import _google_event, _graph_event
from mind.integrations.mail import _gmail_message, _graph_message
from mind.integrations.providers import client_credentials, get_provider, is_configured
from mind.integrations.store import _apply_token_data


class TestCrypto:

    def test_roundtrip(self):
        token = "secret-token-123"
        blob = crypto.encrypt(token)
        assert blob and blob != token
        assert crypto.decrypt(blob) == token

    def test_empty(self):
        assert crypto.encrypt("") == ""
        assert crypto.decrypt("") == ""

    def test_invalid_returns_empty(self):
        assert crypto.decrypt("no-es-un-token-fernet") == ""


class TestState:

    def test_sign_and_read(self):
        token = state.make_state(7, "outlook", "admin")
        data = state.read_state(token)
        assert data["tid"] == 7
        assert data["p"] == "outlook"
        assert data["o"] == "admin"

    def test_tampered_returns_none(self):
        assert state.read_state("firma.invalida.aqui") is None


class TestProviders:

    def test_known(self):
        assert get_provider("outlook").key == "outlook"
        assert get_provider("google").key == "google"
        assert get_provider("desconocido") is None

    def test_is_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "MS_CLIENT_ID", "cid", raising=False)
        monkeypatch.setattr(settings, "MS_CLIENT_SECRET", "sec", raising=False)
        assert is_configured("outlook") is True
        monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "", raising=False)
        assert is_configured("google") is False
        assert client_credentials("outlook") == ("cid", "sec")


class TestMailNormalizers:

    def test_graph_message(self):
        m = {
            "id": "A1",
            "subject": "Hola",
            "from": {"emailAddress": {"address": "a@x.com", "name": "Ana"}},
            "toRecipients": [{"emailAddress": {"address": "b@y.com"}}],
            "receivedDateTime": "2026-10-05T12:00:00Z",
            "bodyPreview": "preview",
            "isRead": False,
            "body": {"contentType": "html", "content": "<p>Hola <b>mundo</b></p>"},
        }
        out = _graph_message(m)
        assert out["id"] == "A1"
        assert out["from"] == "a@x.com"
        assert out["to"] == ["b@y.com"]
        assert "Hola" in out["body"] and "<" not in out["body"]
        assert out["is_read"] is False

    def test_gmail_message(self):
        raw = base64.urlsafe_b64encode(b"Cuerpo del correo").decode().rstrip("=")
        m = {
            "id": "G1",
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": "snip",
            "internalDate": "1728000000000",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "Subject", "value": "Asunto"},
                    {"name": "From", "value": "c@z.com"},
                    {"name": "To", "value": "d@w.com"},
                ],
                "body": {"data": raw},
            },
        }
        out = _gmail_message(m)
        assert out["subject"] == "Asunto"
        assert out["from"] == "c@z.com"
        assert out["body"] == "Cuerpo del correo"
        assert out["is_read"] is False  # UNREAD presente


class TestCalendarNormalizers:

    def test_graph_event(self):
        e = {
            "subject": "Reunión",
            "start": {"dateTime": "2026-10-05T14:00:00"},
            "end": {"dateTime": "2026-10-05T15:00:00"},
            "location": {"displayName": "Sala 1"},
            "organizer": {"emailAddress": {"address": "jefe@x.com"}},
            "attendees": [{"emailAddress": {"address": "yo@x.com"}}],
        }
        out = _graph_event(e)
        assert out["title"] == "Reunión"
        assert out["location"] == "Sala 1"
        assert out["organizer"] == "jefe@x.com"
        assert out["attendees"] == ["yo@x.com"]

    def test_google_event(self):
        e = {
            "summary": "Cita",
            "start": {"dateTime": "2026-10-05T09:00:00-05:00"},
            "end": {"dateTime": "2026-10-05T09:30:00-05:00"},
            "organizer": {"email": "a@b.com"},
            "attendees": [{"email": "c@d.com"}],
        }
        out = _google_event(e)
        assert out["title"] == "Cita"
        assert out["attendees"] == ["c@d.com"]


class TestTokenApply:

    def test_sets_expiry_and_status(self):
        conn = SimpleNamespace(
            access_token_encrypted="", refresh_token_encrypted=None,
            token_expires_at=None, scopes="", status="error", last_error="x",
        )
        _apply_token_data(conn, {
            "access_token": "at", "refresh_token": "rt", "expires_in": 3600,
            "scope": "Mail.Read",
        })
        assert conn.access_token_encrypted != "at"  # cifrado
        assert conn.refresh_token_encrypted
        assert conn.token_expires_at is not None
        assert conn.status == "connected"
        assert conn.last_error is None
        assert crypto.decrypt(conn.access_token_encrypted) == "at"

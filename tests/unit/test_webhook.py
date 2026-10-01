"""
Tests de resolución de URL de webhook (auto-reparación de bots).
"""
from __future__ import annotations

from mind.config import settings
from mind.telegram.bot import _resolve_webhook_base, webhook_full_url


class TestWebhookBase:

    def test_prefers_env_url(self, monkeypatch):
        monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_URL", "https://prod.example.app", raising=False)
        assert _resolve_webhook_base("https://tenant.example") == "https://prod.example.app"

    def test_falls_back_to_tenant_url(self, monkeypatch):
        monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_URL", "https://example.com", raising=False)
        assert _resolve_webhook_base("https://tenant.example/") == "https://tenant.example"

    def test_none_when_missing(self, monkeypatch):
        monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_URL", "", raising=False)
        assert _resolve_webhook_base(None) == ""

    def test_full_url(self, monkeypatch):
        monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_URL", "https://prod.example.app", raising=False)
        assert webhook_full_url("123:abc", None) == "https://prod.example.app/webhook/123:abc"

    def test_full_url_empty_base(self, monkeypatch):
        monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_URL", "https://example.com", raising=False)
        assert webhook_full_url("123:abc", None) == ""

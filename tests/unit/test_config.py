"""
Tests unitarios para mind/config.py.
Requisitos: 9.1, 10.3
"""
import pytest
from pydantic import ValidationError


REQUIRED_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_URL",
    "OPENAI_API_KEY",
    "DATABASE_URL",
    "DATABASE_URL_SYNC",
]

BASE_ENV = {
    "TELEGRAM_BOT_TOKEN": "test_token",
    "TELEGRAM_WEBHOOK_URL": "https://example.com",
    "OPENAI_API_KEY": "sk-test123",
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
    "DATABASE_URL_SYNC": "postgresql://user:pass@localhost:5432/db",
    "PORT": "8000",
}


def test_settings_loads_with_all_required_vars(monkeypatch):
    """Settings se instancia correctamente con todas las variables presentes."""
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)

    from mind.config import Settings
    s = Settings()
    assert s.TELEGRAM_BOT_TOKEN == "test_token"
    assert s.OPENAI_MODEL == "gpt-4o"     # default
    assert s.CONVERSATION_WINDOW == 20    # default


@pytest.mark.parametrize("missing_var", REQUIRED_VARS)
def test_settings_fails_when_required_var_missing(monkeypatch, missing_var):
    """La ausencia de cualquier variable obligatoria levanta ValidationError."""
    for key, value in BASE_ENV.items():
        if key != missing_var:
            monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing_var, raising=False)

    from mind.config import Settings
    with pytest.raises((ValidationError, Exception)):
        Settings()


def test_conversation_window_rejects_below_range(monkeypatch):
    """CONVERSATION_WINDOW rechaza valores fuera del rango [1, 100]."""
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVERSATION_WINDOW", "0")  # fuera de rango

    from mind.config import Settings
    with pytest.raises((ValidationError, Exception)):
        Settings()


def test_conversation_window_rejects_above_range(monkeypatch):
    """CONVERSATION_WINDOW rechaza valores mayores a 100."""
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CONVERSATION_WINDOW", "101")  # fuera de rango

    from mind.config import Settings
    with pytest.raises((ValidationError, Exception)):
        Settings()


def test_conversation_window_accepts_boundary_values(monkeypatch):
    """CONVERSATION_WINDOW acepta valores en los límites [1, 100]."""
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)

    from mind.config import Settings

    monkeypatch.setenv("CONVERSATION_WINDOW", "1")
    s = Settings()
    assert s.CONVERSATION_WINDOW == 1

    monkeypatch.setenv("CONVERSATION_WINDOW", "100")
    s = Settings()
    assert s.CONVERSATION_WINDOW == 100


def test_default_values_are_correct(monkeypatch):
    """Los valores por defecto son correctos."""
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)

    from mind.config import Settings
    s = Settings()
    assert s.OPENAI_MODEL == "gpt-4o"
    assert s.OPENAI_TIMEOUT_SECONDS == 60
    assert s.CONVERSATION_WINDOW == 20
    assert s.AGENT_MAX_TOOL_CYCLES == 5
    assert s.MAX_MESSAGE_CHARS == 32_000
    assert s.CLIENT_NAME == "Versat"
    assert s.CLIENT_LOGO_PATH is None
    assert s.PORT == 8000

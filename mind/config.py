"""
Configuración central de Mind by Versat.
"""
import sys
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_URL: str
    ADMIN_CHAT_ID: int

    # --- OpenAI / OpenRouter ---
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENAI_MODEL: str = "openai/gpt-4o-mini"
    OPENAI_TIMEOUT_SECONDS: int = 60

    # --- PostgreSQL ---
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # PostgreSQL Railway — OFIMA backups, solo lectura
    OFIMA_DATABASE_URL: str = ""

    # --- OFIMA SQL Server ---
    SQLSERVER_HOST: str = "172.200.231.95"
    SQLSERVER_DB: str = "MICELU"
    SQLSERVER_USER: str = "db_read"
    SQLSERVER_PASSWORD: str = ""
    SQLSERVER_DRIVER: str = "ODBC Driver 18 for SQL Server"

    # --- Agent ---
    CONVERSATION_WINDOW: int = Field(default=20, ge=1, le=100)
    AGENT_MAX_TOOL_CYCLES: int = Field(default=5, ge=1, le=20)
    MAX_MESSAGE_CHARS: int = Field(default=32_000, ge=1)

    # --- Reports ---
    CLIENT_NAME: str = "Versat"
    CLIENT_LOGO_PATH: str | None = None

    # --- Server ---
    PORT: int = Field(default=8000, ge=1, le=65535)

    # --- Panel de administración ---
    ADMIN_USER: str = "admin"
    ADMIN_PASSWORD: str = "admin1234"
    ADMIN_SECRET_KEY: str = "cambia_esto_por_una_clave_secreta_larga"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


def get_settings() -> Settings:
    try:
        return Settings()
    except Exception as exc:
        print(f"[ERROR] Configuración inválida: {exc}", file=sys.stderr)
        sys.exit(1)


settings = get_settings()

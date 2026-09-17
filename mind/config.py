"""
Configuración central de Mind by Versat.
Las variables TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_URL, ADMIN_CHAT_ID y
SQLSERVER_* del .env se usan para inicializar el tenant por defecto en la
primera migración. En runtime, la configuración de cada tenant viene de BD.
"""
import sys
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- OpenAI / OpenRouter ---
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENAI_MODEL: str = "openai/gpt-4o-mini"
    OPENAI_TIMEOUT_SECONDS: int = 60

    # --- PostgreSQL (app interna) ---
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # --- Tenant por defecto (se usa en migración y como fallback) ---
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_URL: str = "https://example.com"
    ADMIN_CHAT_ID: int = 0

    # --- SQL Server OFIMA (tenant por defecto) ---
    SQLSERVER_HOST: str = ""
    SQLSERVER_DB: str = ""
    SQLSERVER_USER: str = ""
    SQLSERVER_PASSWORD: str = ""
    SQLSERVER_DRIVER: str = "ODBC Driver 18 for SQL Server"

    # --- Agent defaults (se sobreescriben por AgentConfig en BD) ---
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

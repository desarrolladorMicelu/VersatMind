"""asegura la tabla telegram_chats (recuperación tras el choque de 0011/0012)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-01 00:00:00.000000

Contexto: hubo un choque de numeración de migraciones. En producción la
revisión 0011 quedó aplicada como `report_config`, por lo que la creación de
`telegram_chats` (que luego quedó etiquetada como 0011) nunca se ejecutó.

Esta migración crea `telegram_chats` de forma idempotente:
  - En producción: la tabla no existe, así que se crea aquí.
  - En una base nueva: la 0011 ya la crea, así que aquí no hace nada.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_chats (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            chat_id BIGINT NOT NULL,
            chat_type TEXT NOT NULL DEFAULT 'private',
            title TEXT,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_telegram_chats_tenant_chat UNIQUE (tenant_id, chat_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_telegram_chats_tenant ON telegram_chats (tenant_id)"
    )


def downgrade() -> None:
    # No se elimina la tabla en downgrade para no perder el registro de chats
    # que pudo haberse creado por la revisión 0011. Es una migración de
    # recuperación idempotente.
    pass

"""telegram chats registry (destinos de prompts programados)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-30 00:00:00.000000

Registra los chats (usuarios y grupos) que el bot ha visto, para poder
elegir el destino de los prompts programados desde una lista amigable.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_chats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_type", sa.Text(), nullable=False, server_default="private"),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("last_name", sa.Text(), nullable=True),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "chat_id", name="uq_telegram_chats_tenant_chat"),
    )
    op.create_index("idx_telegram_chats_tenant", "telegram_chats", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_telegram_chats_tenant", table_name="telegram_chats")
    op.drop_table("telegram_chats")

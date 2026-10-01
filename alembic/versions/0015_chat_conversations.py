"""chat_conversations table (interfaz web de chat)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-01 00:00:00.000000

Conversaciones de la interfaz web de chat (tipo Claude). Cada conversación
usa un chat_id sintético para reutilizar `conversation_history` como memoria.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default="Nueva conversación"),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "chat_id", name="uq_chat_conversations_tenant_chat"),
    )
    op.create_index(
        "idx_chat_conversations_tenant_owner",
        "chat_conversations",
        ["tenant_id", "owner", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_chat_conversations_tenant_owner", table_name="chat_conversations")
    op.drop_table("chat_conversations")

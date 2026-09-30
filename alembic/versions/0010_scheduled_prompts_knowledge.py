"""scheduled prompts and per-tenant knowledge base

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-30 00:00:00.000000

Agrega:
  - tabla scheduled_prompts (prompts programados que envían por Telegram)
  - tabla knowledge_entries (base de conocimiento por cliente)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── scheduled_prompts ─────────────────────────────────────────────────
    op.create_table(
        "scheduled_prompts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_label", sa.Text(), nullable=True),
        sa.Column("frequency", sa.Text(), nullable=False, server_default="daily"),
        sa.Column("cron_expression", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="America/Bogota"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "idx_scheduled_prompts_tenant_active",
        "scheduled_prompts",
        ["tenant_id", "is_active"],
    )

    # ── knowledge_entries ─────────────────────────────────────────────────
    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
    )
    op.create_index(
        "idx_knowledge_entries_tenant",
        "knowledge_entries",
        ["tenant_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_entries_tenant", table_name="knowledge_entries")
    op.drop_table("knowledge_entries")
    op.drop_index("idx_scheduled_prompts_tenant_active", table_name="scheduled_prompts")
    op.drop_table("scheduled_prompts")

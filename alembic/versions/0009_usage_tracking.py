"""token usage tracking, alerts and per-tenant usage settings

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30 00:00:00.000000

Agrega:
  - columnas de pausa por consumo a la tabla users
  - tabla token_usage (consumo por interacción)
  - tabla usage_alerts (alertas por umbral superado)
  - tabla usage_settings (configuración de umbral/notificaciones por tenant)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users: pausa por consumo ──────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("users", sa.Column("paused_reason", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))

    # ── token_usage ───────────────────────────────────────────────────────
    op.create_table(
        "token_usage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=False, server_default=""),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source", sa.Text(), nullable=False, server_default="chat"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_token_usage_tenant_created", "token_usage", ["tenant_id", "created_at"]
    )
    op.create_index(
        "idx_token_usage_tenant_chat",
        "token_usage",
        ["tenant_id", "chat_id", "created_at"],
    )

    # ── usage_alerts ──────────────────────────────────────────────────────
    op.create_table(
        "usage_alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("threshold_usd", sa.Float(), nullable=False, server_default="8"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("period_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("notified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_usage_alerts_tenant_status", "usage_alerts", ["tenant_id", "status"]
    )
    op.create_index(
        "idx_usage_alerts_tenant_chat", "usage_alerts", ["tenant_id", "chat_id"]
    )

    # ── usage_settings ────────────────────────────────────────────────────
    op.create_table(
        "usage_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("threshold_usd", sa.Float(), nullable=False, server_default="8"),
        sa.Column("period", sa.Text(), nullable=False, server_default="month"),
        sa.Column("auto_pause", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notify_telegram", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_email", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("admin_email", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_index("idx_usage_settings_tenant", "usage_settings", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_usage_settings_tenant", table_name="usage_settings")
    op.drop_table("usage_settings")

    op.drop_index("idx_usage_alerts_tenant_chat", table_name="usage_alerts")
    op.drop_index("idx_usage_alerts_tenant_status", table_name="usage_alerts")
    op.drop_table("usage_alerts")

    op.drop_index("idx_token_usage_tenant_chat", table_name="token_usage")
    op.drop_index("idx_token_usage_tenant_created", table_name="token_usage")
    op.drop_table("token_usage")

    op.drop_column("users", "paused_at")
    op.drop_column("users", "paused_reason")
    op.drop_column("users", "is_paused")

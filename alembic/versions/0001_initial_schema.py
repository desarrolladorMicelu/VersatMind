"""initial_schema

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- roles ---
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # --- role_permissions ---
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_name", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_name"),
    )

    # --- users ---
    op.create_table(
        "users",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("role_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("chat_id"),
    )

    # --- conversation_history ---
    op.create_table(
        "conversation_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column("tool_call_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_conv_history_chat_id",
        "conversation_history",
        ["chat_id", "created_at"],
    )

    # --- scheduled_tasks ---
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cron_expression", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="America/Bogota"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("last_execution_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_scheduled_tasks_chat_id",
        "scheduled_tasks",
        ["chat_id"],
    )

    # --- audit_log ---
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "timestamp_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("request_content", sa.Text(), nullable=True),
        sa.Column("tool_invoked", sa.Text(), nullable=True),
        sa.Column("tool_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_result", sa.Text(), nullable=True),
        sa.Column("response_content", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("error_description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_audit_log_chat_id",
        "audit_log",
        ["chat_id", "timestamp_utc"],
    )
    op.create_index(
        "idx_audit_log_timestamp",
        "audit_log",
        ["timestamp_utc"],
    )


def downgrade() -> None:
    op.drop_index("idx_audit_log_timestamp", table_name="audit_log")
    op.drop_index("idx_audit_log_chat_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("idx_scheduled_tasks_chat_id", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
    op.drop_index("idx_conv_history_chat_id", table_name="conversation_history")
    op.drop_table("conversation_history")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("roles")

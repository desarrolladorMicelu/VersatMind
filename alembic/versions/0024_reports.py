"""reports HTML del chat web

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-23 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False, server_default=""),
        sa.Column("report_type", sa.Text(), nullable=False, server_default="dashboard"),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_reports_tenant_owner", "reports", ["tenant_id", "owner", "created_at"]
    )
    op.create_index(
        "idx_reports_conversation", "reports", ["conversation_id", "message_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_reports_conversation", table_name="reports")
    op.drop_index("idx_reports_tenant_owner", table_name="reports")
    op.drop_table("reports")

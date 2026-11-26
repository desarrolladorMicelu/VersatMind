"""portal_users + memberships + Telegram link

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-26 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portal_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("temp_password_enc", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_portal_users_username"),
    )
    op.create_index("idx_portal_users_active", "portal_users", ["is_active"])

    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portal_user_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["portal_user_id"], ["portal_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portal_user_id", "tenant_id", name="uq_membership_user_tenant"),
    )
    op.create_index("idx_memberships_tenant", "memberships", ["tenant_id", "is_active"])

    op.add_column("users", sa.Column("portal_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_portal_user", "users", "portal_users",
        ["portal_user_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("idx_users_portal_user", "users", ["portal_user_id"])


def downgrade() -> None:
    op.drop_index("idx_users_portal_user", table_name="users")
    op.drop_constraint("fk_users_portal_user", "users", type_="foreignkey")
    op.drop_column("users", "portal_user_id")
    op.drop_index("idx_memberships_tenant", table_name="memberships")
    op.drop_table("memberships")
    op.drop_index("idx_portal_users_active", table_name="portal_users")
    op.drop_table("portal_users")

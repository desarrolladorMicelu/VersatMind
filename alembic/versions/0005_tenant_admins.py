"""tenant_admins table

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-17 00:00:00.000000

Crea la tabla tenant_admins para que cada tenant tenga sus propias
cuentas de acceso al panel de administración.
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_admins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tenant_admins_tenant", "tenant_admins", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_tenant_admins_tenant", table_name="tenant_admins")
    op.drop_table("tenant_admins")

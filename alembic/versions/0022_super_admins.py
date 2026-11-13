"""superadmins table

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-11 00:00:00.000000

Crea la tabla superadmins para que el superadmin raíz (.env) pueda crear
más cuentas de superadministrador desde el panel. Estas cuentas tienen
acceso total a todos los tenants.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "superadmins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_superadmins_username"),
    )


def downgrade() -> None:
    op.drop_table("superadmins")

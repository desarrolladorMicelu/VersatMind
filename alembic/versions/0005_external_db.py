"""add external_db JSONB column to tenants

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-23 00:00:00.000000

Agrega la columna JSONB `external_db` a la tabla tenants para soportar
bases de datos externas genéricas (PostgreSQL ahora, MySQL después).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("external_db", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "external_db")
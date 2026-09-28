"""add external_alegra JSONB column to tenants

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-28 00:00:00.000000

Agrega la columna JSONB `external_alegra` a la tabla tenants para soportar
la integración con Alegra vía MCP.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("external_alegra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "external_alegra")
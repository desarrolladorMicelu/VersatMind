"""add external_sheets JSONB column to tenants

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-23 00:00:00.000000

Agrega la columna JSONB `external_sheets` a la tabla tenants para soportar
Google Sheets como fuente de datos externa.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("external_sheets", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "external_sheets")
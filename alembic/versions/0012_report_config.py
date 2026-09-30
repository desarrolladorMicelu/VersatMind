"""add report_config JSONB column to tenants

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30 00:00:00.000000

Agrega la columna JSONB `report_config` a la tabla tenants para soportar
la configuración de informes contables personalizados por tenant.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("report_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "report_config")
"""add external_excel JSONB column to tenants

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-09 22:30:00.000000

Columna para configurar acceso a archivos Excel via OneDrive/SharePoint.
Contiene tokens OAuth2, file_id y schema_description.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("external_excel", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "external_excel")
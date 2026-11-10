"""add language column to meetings (idioma del STT)

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-28 00:35:00.000000

El modelo de transcripción recibe el idioma (es/en) para no auto-detectarlo.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("language", sa.Text(), nullable=False, server_default="es"),
    )


def downgrade() -> None:
    op.drop_column("meetings", "language")
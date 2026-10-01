"""add send_to_all to scheduled_prompts

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-01 00:00:00.000000

Permite que un prompt programado se envíe a todos los contactos conocidos
del tenant, no a un único chat.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scheduled_prompts",
        sa.Column(
            "send_to_all",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("scheduled_prompts", "send_to_all")

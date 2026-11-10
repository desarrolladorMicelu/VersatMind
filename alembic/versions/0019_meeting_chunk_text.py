"""add text column to meeting_audio_chunks (transcripción por chunk)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-27 23:20:00.000000

Cada chunk guarda su propia transcripción para que `finalize_meeting`
reconstruya el transcript final de forma determinista (sin carreras con las
tareas de transcripción incremental).
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"


def upgrade() -> None:
    op.add_column(
        "meeting_audio_chunks",
        sa.Column("text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meeting_audio_chunks", "text")
"""add stt_provider and diarize columns to meetings

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-10 03:05:00.000000

stt_provider → "deepgram" (default) | "openrouter"
diarize → True: desktop (full audio, Speaker 0/1), False: web (per‑chunk live)
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("stt_provider", sa.Text(), nullable=False, server_default="deepgram"),
    )
    op.add_column(
        "meetings",
        sa.Column("diarize", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("meetings", "diarize")
    op.drop_column("meetings", "stt_provider")
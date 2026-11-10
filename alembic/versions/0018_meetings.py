"""add meetings and meeting_audio_chunks tables

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-27 22:50:00.000000

Tablas para el módulo de Reuniones: grabación por chunks (BYTEA),
transcripción y resumen, scoped por tenant_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False, server_default=""),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="recording"),
        sa.Column("audio_format", sa.Text(), nullable=False, server_default="webm"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_meetings_tenant_created", "meetings", ["tenant_id", "created_at"]
    )

    op.create_table(
        "meeting_audio_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("meeting_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transcribed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "seq", name="uq_audio_chunks_meeting_seq"),
    )
    op.create_index(
        "idx_audio_chunks_meeting_seq", "meeting_audio_chunks", ["meeting_id", "seq"]
    )


def downgrade() -> None:
    op.drop_index("idx_audio_chunks_meeting_seq", table_name="meeting_audio_chunks")
    op.drop_table("meeting_audio_chunks")
    op.drop_index("idx_meetings_tenant_created", table_name="meetings")
    op.drop_table("meetings")
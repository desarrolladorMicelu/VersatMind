"""Schemas Pydantic del módulo de Reuniones."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MeetingCreate(BaseModel):
    title: str
    # Idioma de la reunión para el STT (ISO-639-1): "es" | "en"
    language: str = "es"
    # Proveedor STT: "deepgram" (default) | "openrouter"
    stt_provider: str = "deepgram"
    # Diarización hablantes: True (desktop, full audio al final), False (web, live per‑chunk)
    diarize: bool = False


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_by: str
    title: str
    language: str
    stt_provider: str
    diarize: bool
    status: str
    audio_format: str
    duration_seconds: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    transcript: str | None = None
    summary: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChunkResponse(BaseModel):
    ok: bool = True
    seq: int


class FinishResponse(BaseModel):
    ok: bool = True
    status: str
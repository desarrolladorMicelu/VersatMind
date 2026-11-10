"""
API REST del módulo de Reuniones — /api/admin/meetings/*
Multi-tenant: todos los endpoints resuelven el tenant efectivo con
`get_effective_tenant_id` y validan que la reunión pertenezca a ese tenant.

Flujo:
  POST /            → crea reunión (status=recording), 409 si hay una activa
  POST /{id}/chunks → sube un chunk de audio incremental (BYTEA)
  POST /{id}/finish → status=processing y lanza transcripción/resumen
  GET  /{id}/audio  → audio concatenado de los chunks (para <audio>)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mind.admin.auth import get_effective_tenant_id, require_admin
from mind.config import settings
from mind.meetings.audio_utils import merge_wav_chunks
from mind.db.base import get_session
from mind.db.models import Meeting, MeetingAudioChunk
from mind.meetings.schemas import ChunkResponse, FinishResponse, MeetingCreate, MeetingOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/meetings", tags=["meetings"])

# Límite por chunk: los chunks se transcriben individualmente y el proveedor
# STT tiene límites de tamaño/timing; 5 MB cubre ~15-60 s cómodamente.
MAX_CHUNK_BYTES = 5 * 1024 * 1024
# Guía anti-abuso: ~10 h de sesiones de 15 s.
MAX_CHUNKS_PER_MEETING = 2400

_MIME_BY_FORMAT = {
    "webm": "audio/webm",
    "mp4": "audio/mp4",
    "m4a": "audio/mp4",
    "wav": "audio/wav",
}


def _mime_for(audio_format: str) -> str:
    return _MIME_BY_FORMAT.get(audio_format or "", "application/octet-stream")


def _meeting_dict(m: Meeting) -> dict:
    return MeetingOut.model_validate(m).model_dump(mode="json")


async def _get_meeting(session: AsyncSession, meeting_id: int, tid: int) -> Meeting:
    m = (await session.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.tenant_id == tid)
    )).scalar_one_or_none()
    if m is None:
        raise HTTPException(status_code=404, detail="Reunión no encontrada")
    return m


@router.get("")
async def meetings_list(
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = None,
):
    tid = get_effective_tenant_id(admin, tenant_id)
    rows = (await session.execute(
        select(Meeting)
        .where(Meeting.tenant_id == tid)
        .order_by(Meeting.created_at.desc())
    )).scalars().all()
    return [_meeting_dict(m) for m in rows]


@router.post("", response_model=MeetingOut, status_code=201)
async def meeting_create(
    body: MeetingCreate,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = None,
):
    tid = get_effective_tenant_id(admin, tenant_id)
    active = (await session.execute(
        select(Meeting).where(
            Meeting.tenant_id == tid,
            Meeting.status.in_(("recording", "processing")),
        ).limit(1)
    )).scalar_one_or_none()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail="Ya hay una reunión en curso para este cliente",
        )

    title = (body.title or "").strip()[:200] or "Reunión sin título"
    language = (body.language or "").strip().lower()
    if language not in ("es", "en"):
        language = "es"

    stt_provider = (body.stt_provider or "").strip().lower()
    if stt_provider not in ("deepgram", "openrouter"):
        stt_provider = "deepgram"
    # Fallback automático si no hay clave Deepgram
    if stt_provider == "deepgram" and not settings.DEEPGRAM_API_KEY:
        logger.warning(
            "DEEPGRAM_API_KEY no configurado → usando OpenRouter"
        )
        stt_provider = "openrouter"

    meeting = Meeting(
        tenant_id=tid,
        created_by=str(admin.get("sub") or "admin"),
        title=title,
        language=language,
        stt_provider=stt_provider,
        diarize=bool(body.diarize) if stt_provider == "deepgram" else False,
        status="recording",
        audio_format="webm",
    )
    session.add(meeting)
    await session.commit()
    await session.refresh(meeting)
    logger.info(
        "Reunión creada id=%s tenant=%s por %s",
        meeting.id, tid, meeting.created_by,
    )
    return _meeting_dict(meeting)


@router.get("/{meeting_id}", response_model=MeetingOut)
async def meeting_detail(
    meeting_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = None,
):
    tid = get_effective_tenant_id(admin, tenant_id)
    meeting = await _get_meeting(session, meeting_id, tid)
    return _meeting_dict(meeting)


@router.post("/{meeting_id}/chunks", response_model=ChunkResponse)
async def meeting_upload_chunk(
    meeting_id: int,
    seq: int = Form(...),
    duration_ms: int = Form(0),
    silent: int = Form(0),
    audio: UploadFile = File(...),
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = None,
):
    """
    Sube un chunk de audio (BYTEA). Idempotente por (meeting_id, seq).
    `silent=1` (VAD del navegador): el chunk es silencio → se marca como
    transcrito vacío sin llamar al STT (evita alucinaciones de Whisper).
    """
    tid = get_effective_tenant_id(admin, tenant_id)
    meeting = await _get_meeting(session, meeting_id, tid)

    if meeting.status != "recording":
        raise HTTPException(
            status_code=409,
            detail=f"La reunión no acepta chunks ({meeting.status})",
        )

    count = len((await session.execute(
        select(MeetingAudioChunk.id).where(
            MeetingAudioChunk.meeting_id == meeting_id
        )
    )).scalars().all())
    if count >= MAX_CHUNKS_PER_MEETING:
        raise HTTPException(status_code=413, detail="Límite de chunks alcanzado")

    data = await audio.read(MAX_CHUNK_BYTES + 1)
    if len(data) > MAX_CHUNK_BYTES:
        raise HTTPException(status_code=413, detail="Chunk demasiado grande (máx 5 MB)")

    if not data:
        raise HTTPException(status_code=400, detail="Chunk vacío")

    # Formato del audio según el navegador (WAV de Web Audio, webm o mp4)
    if meeting.audio_format in ("webm", "wav"):
        content_type = (audio.content_type or "").lower()
        if "mp4" in content_type or "m4a" in content_type or "aac" in content_type:
            meeting.audio_format = "mp4"
        elif "wav" in content_type or "wave" in content_type:
            meeting.audio_format = "wav"

    meeting.updated_at = datetime.now(timezone.utc)

    # Chunks con diarize=true (desktop): se marcan transcritos-vacío inmediatamente
    # (no hay STP por chunk). Los demás se transcriben per‑chunk en vivo.
    skip_live = meeting.stt_provider == "deepgram" and meeting.diarize

    stmt = pg_insert(MeetingAudioChunk).values(
        meeting_id=meeting_id,
        seq=seq,
        data=data,
        duration_ms=max(0, duration_ms),
        transcribed=bool(skip_live),
        text="" if skip_live else None,
    ).on_conflict_do_nothing(constraint="uq_audio_chunks_meeting_seq")
    await session.execute(stmt)
    await session.commit()

    if not skip_live and not bool(silent):
        chunk_row = (await session.execute(
            select(MeetingAudioChunk).where(
                MeetingAudioChunk.meeting_id == meeting_id,
                MeetingAudioChunk.seq == seq,
            )
        )).scalar_one_or_none()
        if chunk_row is not None:
            from mind.meetings.service import transcribe_chunk_task
            asyncio.create_task(transcribe_chunk_task(meeting_id, chunk_row.id))

    return {"ok": True, "seq": seq}


@router.post("/{meeting_id}/finish", response_model=FinishResponse)
async def meeting_finish(
    meeting_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = None,
):
    """
    Finaliza la grabación: recording → processing y lanza en background
    la transcripción de chunks pendientes + generación del resumen.
    Es idempotente: si ya está processing/ready/error, no re-procesa.
    """
    tid = get_effective_tenant_id(admin, tenant_id)
    meeting = await _get_meeting(session, meeting_id, tid)

    if meeting.status not in ("recording", "processing"):
        return {"ok": True, "status": meeting.status}

    meeting.status = "processing"
    meeting.finished_at = datetime.now(timezone.utc)
    await session.commit()

    from mind.meetings.service import finalize_meeting
    asyncio.create_task(finalize_meeting(meeting_id))
    return {"ok": True, "status": "processing"}


@router.get("/{meeting_id}/transcript")
async def meeting_transcript(
    meeting_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = None,
):
    """
    Transcripción parcial EN VIVO mientras se graba: junta los textos de los
    chunks ya transcritos (chunk.text) en orden de seq.
    """
    tid = get_effective_tenant_id(admin, tenant_id)
    await _get_meeting(session, meeting_id, tid)
    chunks = (await session.execute(
        select(MeetingAudioChunk)
        .where(MeetingAudioChunk.meeting_id == meeting_id)
        .order_by(MeetingAudioChunk.seq.asc())
    )).scalars().all()
    transcript = "\n".join(
        c.text.strip() for c in chunks if c.transcribed and (c.text or "").strip()
    )
    return {
        "transcript": transcript,
        "segments": [
            {"seq": c.seq, "text": c.text or ""}
            for c in chunks if c.transcribed
        ],
    }





@router.get("/{meeting_id}/audio")
async def meeting_audio(
    meeting_id: int,
    admin=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    tenant_id: int | None = None,
):
    """
    Audio de la reunión. Para WAV une los chunks en un archivo válido (el
    navegador lo reproduce con un solo <audio>). Para otros formatos concatena.
    """
    tid = get_effective_tenant_id(admin, tenant_id)
    meeting = await _get_meeting(session, meeting_id, tid)

    chunks = (await session.execute(
        select(MeetingAudioChunk)
        .where(MeetingAudioChunk.meeting_id == meeting_id)
        .order_by(MeetingAudioChunk.seq.asc())
    )).scalars().all()

    if not chunks:
        raise HTTPException(status_code=404, detail="No hay audio para esta reunión")

    if meeting.audio_format == "wav":
        audio = merge_wav_chunks([bytes(c.data) for c in chunks])
    else:
        audio = b"".join(bytes(c.data) for c in chunks)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": (
            f'inline; filename="meeting-{meeting_id}.{meeting.audio_format}"'
        ),
        "Cache-Control": "no-store",
    }
    return Response(
        content=audio,
        media_type=_mime_for(meeting.audio_format),
        headers=headers,
    )
"""
Servicio de procesamiento de reuniones.

Comportamiento según provider:
- openrouter: transcripción per‑chunk con OpenRouter, rebuild al final (flujo actual).
- deepgram + diarize=false: transcripción per‑chunk con Deepgram (texto plano),
  rebuild al final (web, live).
- deepgram + diarize=true: sin per‑chunk; al finalizar se concatena el audio
  completo y se envía a Deepgram con diarización (desktop, Speaker 0/1).

Cada tarea abre SU PROPIA sesión de BD con `_session_factory()`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from mind.db.base import _session_factory
from mind.db.models import Meeting, MeetingAudioChunk
from mind.meetings.audio_utils import merge_wav_chunks
from mind.meetings.transcriber import transcribe_audio

logger = logging.getLogger(__name__)

STALE_RECORDING_MINUTES = 3
STALE_PROCESSING_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rebuild_transcript(chunks: list) -> str:
    """Concatena los textos de los chunks transcritos, en orden de seq."""
    return "\n".join(
        c.text.strip() for c in chunks
        if c.transcribed and (c.text or "").strip()
    )


async def transcribe_chunk_task(meeting_id: int, chunk_id: int) -> None:
    """Transcribe UN chunk con el proveedor del meeting. Salta si es diarize."""
    if _session_factory is None:
        return
    async with _session_factory() as session:
        chunk = (await session.execute(
            select(MeetingAudioChunk).where(MeetingAudioChunk.id == chunk_id)
        )).scalar_one_or_none()
        if chunk is None or chunk.transcribed:
            return

        meeting = (await session.execute(
            select(Meeting).where(Meeting.id == meeting_id)
        )).scalar_one_or_none()
        if meeting is None or meeting.status != "recording":
            return

        # deepgram + diarize=true: no transcribir por chunk
        if meeting.stt_provider == "deepgram" and meeting.diarize:
            chunk.transcribed = True
            chunk.text = ""
            await session.commit()
            return

        try:
            text = await transcribe_audio(
                bytes(chunk.data),
                meeting.audio_format,
                meeting.language,
                meeting.stt_provider,
                False,
            )
            chunk.transcribed = True
            chunk.text = text
            await session.commit()
            logger.info(
                "Chunk %s (meeting %s) transcrito: %d chars", chunk_id, meeting_id, len(text),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error transcribiendo chunk %s meeting %s: %s",
                chunk_id, meeting_id, type(exc).__name__,
            )


async def finalize_meeting(meeting_id: int) -> None:
    """Pipeline final según el provider del meeting."""
    if _session_factory is None:
        return

    try:
        async with _session_factory() as session:
            meeting = (await session.execute(
                select(Meeting).where(Meeting.id == meeting_id).with_for_update()
            )).scalar_one_or_none()
            if meeting is None or meeting.status not in ("recording", "processing"):
                return
            meeting.status = "processing"
            meeting.finished_at = meeting.finished_at or _now()
            await session.commit()

            chunks = (await session.execute(
                select(MeetingAudioChunk)
                .where(MeetingAudioChunk.meeting_id == meeting_id)
                .order_by(MeetingAudioChunk.seq.asc())
            )).scalars().all()

            total_ms = sum(c.duration_ms or 0 for c in chunks)
            meeting.duration_seconds = round(total_ms / 1000)

            if not chunks:
                meeting.error_message = "No se recibió audio"
                meeting.status = "ready"
                meeting.updated_at = _now()
                await session.commit()
                return

            # ── Rama Deepgram + diarize=true: audio completo con diarización ──
            if meeting.stt_provider == "deepgram" and meeting.diarize:
                try:
                    audio = merge_wav_chunks([bytes(c.data) for c in chunks])
                    meeting.transcript = await transcribe_audio(
                        audio, meeting.audio_format, meeting.language,
                        "deepgram", True,
                    )
                    meeting.status = "ready"
                except Exception as exc:  # noqa: BLE001
                    meeting.status = "error"
                    meeting.error_message = str(exc)[:300] or type(exc).__name__
                    logger.error(
                        "Diarización falló meeting %s: %s", meeting_id, type(exc).__name__,
                    )
                    meeting.updated_at = _now()
                    await session.commit()
                    return

                if meeting.transcript:
                    from mind.meetings.summarizer import generate_summary
                    meeting.summary = await generate_summary(meeting.transcript)
                meeting.updated_at = _now()
                await session.commit()
                logger.info("Reunión %s con diarización finalizada", meeting_id)
                return

            # ── Rama per‑chunk (deepgram sin diarizar u openrouter) ──────────
            failed = 0
            for chunk in chunks:
                if chunk.transcribed:
                    continue
                try:
                    text = await transcribe_audio(
                        bytes(chunk.data), meeting.audio_format, meeting.language,
                        meeting.stt_provider, False,
                    )
                    chunk.transcribed = True
                    chunk.text = text
                    await session.commit()
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    logger.error(
                        "Finalize: chunk %s meeting %s falló: %s",
                        chunk.id, meeting_id, type(exc).__name__,
                    )

            meeting.transcript = _rebuild_transcript(chunks) or None

            if meeting.transcript:
                from mind.meetings.summarizer import generate_summary
                meeting.summary = await generate_summary(meeting.transcript)

            if failed and not (meeting.transcript or "").strip():
                meeting.status = "error"
                meeting.error_message = f"No se pudo transcribir el audio ({failed} segmento(s))"
            else:
                meeting.status = "ready"
                if failed:
                    meeting.error_message = f"{failed} segmento(s) no se pudieron transcribir"
            meeting.updated_at = _now()
            await session.commit()
            logger.info("Reunión %s finalizada: status=%s", meeting_id, meeting.status)

    except Exception as exc:  # noqa: BLE001
        logger.error("finalize_meeting %s falló: %s", meeting_id, type(exc).__name__)
        try:
            async with _session_factory() as session:
                meeting = (await session.execute(
                    select(Meeting).where(Meeting.id == meeting_id)
                )).scalar_one_or_none()
                if meeting is not None:
                    meeting.status = "error"
                    meeting.error_message = str(exc)[:300] or type(exc).__name__
                    meeting.updated_at = _now()
                    await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo marcar reunión %s como error", meeting_id)


async def sweep_stale_meetings() -> None:
    """Auto‑finaliza reuniones huérfanas y marca como error las atascadas."""
    if _session_factory is None:
        return

    now = _now()
    recording_cutoff = now - timedelta(minutes=STALE_RECORDING_MINUTES)
    processing_cutoff = now - timedelta(minutes=STALE_PROCESSING_MINUTES)

    stale_recording: list[Meeting] = []
    async with _session_factory() as session:
        stale_processing = (await session.execute(
            select(Meeting).where(
                Meeting.status == "processing",
                Meeting.updated_at < processing_cutoff,
            )
        )).scalars().all()
        for m in stale_processing:
            m.status = "error"
            m.error_message = "Procesamiento interrumpido"
            m.updated_at = now
            logger.warning("Reunión %s atascada en processing → error", m.id)

        stale_recording = (await session.execute(
            select(Meeting).where(
                Meeting.status == "recording",
                Meeting.updated_at < recording_cutoff,
            )
        )).scalars().all()
        await session.commit()

    for m in stale_recording:
        logger.info("Auto‑finalizando reunión huérfana %s", m.id)
        async with _session_factory() as session:
            meet = (await session.execute(
                select(Meeting).where(Meeting.id == m.id)
            )).scalar_one_or_none()
            if meet is not None and meet.status == "recording":
                meet.status = "processing"
                meet.finished_at = _now()
                await session.commit()
        asyncio.create_task(finalize_meeting(m.id))
"""
Router de transcripción — despacha a OpenRouter o Deepgram según provider.
"""
from __future__ import annotations

import asyncio
import logging

from mind.config import settings

logger = logging.getLogger(__name__)

_EXT_BY_FORMAT = {
    "webm": "webm",
    "ogg": "ogg",
    "opus": "ogg",
    "mp4": "m4a",
    "m4a": "m4a",
    "aac": "aac",
    "mp3": "mp3",
    "wav": "wav",
}

MAX_TRANSCRIBE_BYTES = 24 * 1024 * 1024


class TranscriptionError(Exception):
    """Fallo definitivo al transcribir audio."""


def audio_extension(audio_format: str | None) -> str:
    return _EXT_BY_FORMAT.get((audio_format or "").lower(), "webm")


async def _transcribe_openrouter(audio_bytes: bytes, language: str | None) -> str:
    """Transcribe con OpenRouter /audio/transcriptions (código actual)."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )
    kwargs: dict = {
        "model": settings.OPENAI_STT_MODEL,
        "file": ("audio.webm", audio_bytes),
    }
    if language:
        kwargs["language"] = language
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            result = await client.audio.transcriptions.create(**kwargs)
            text = (result.text or "").strip()
            return text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Intento %d/2 OpenRouter falló: %s", attempt + 1, type(exc).__name__)
            if attempt == 0:
                await asyncio.sleep(1.0)
    raise TranscriptionError(f"Error OpenRouter: {last_error}")


async def transcribe_audio(
    audio_bytes: bytes,
    audio_format: str | None = None,
    language: str | None = None,
    stt_provider: str = "deepgram",
    diarize: bool = False,
) -> str:
    """
    Transcribe audio con el proveedor indicado.

    - openrouter: /audio/transcriptions, cualquier formato.
    - deepgram sin diarizar: POST /v1/listen sin diarize, texto plano (live web).
    - deepgram con diarización: POST /v1/listen con diarize, Speaker 0/1 (desktop).
    """
    if not audio_bytes:
        raise TranscriptionError("Chunk vacío")
    if len(audio_bytes) > MAX_TRANSCRIBE_BYTES:
        raise TranscriptionError(
            f"Audio demasiado grande (máx {MAX_TRANSCRIBE_BYTES // (1024 * 1024)} MB)"
        )

    if stt_provider == "openrouter":
        return await _transcribe_openrouter(audio_bytes, language)

    from mind.meetings.transcriber_deepgram import (
        transcribe_chunk_deepgram,
        transcribe_full_deepgram,
    )

    if diarize:
        return await transcribe_full_deepgram(audio_bytes, language or "es")
    return await transcribe_chunk_deepgram(audio_bytes, language or "es")
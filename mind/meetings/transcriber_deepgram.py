"""
Transcripción con Deepgram API.

Dos modos:
- `transcribe_chunk_deepgram`: per‑chunk (texto plano, sin diarización) para
  live transcript en la web.
- `transcribe_full_deepgram`: audio completo con diarización para obtener
  "Speaker 0 / Speaker 1" en el escritorio.
"""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

from mind.config import settings

logger = logging.getLogger(__name__)

DEEPGRAM_BASE = "https://api.deepgram.com/v1/listen"

# Timeout grande para reuniones completas (full audio puede durar minutos).
_TIMEOUT = max(settings.OPENAI_TIMEOUT_SECONDS, 120)

# Mapa de códigos ISO 639-1 a códigos Deepgram.
# "es" → "es-419" (latinoamericano) para mejor precisión; "en" se queda igual.
_DEEPGRAM_LANG_MAP: dict[str, str] = {"es": "es-419", "en": "en"}


class DeepgramError(Exception):
    """Fallo en la transcripción con Deepgram."""


def _dg_lang(code: str) -> str:
    """Convierte código ISO 639-1 -> Deepgram. fallback: el mismo código."""
    if code in _DEEPGRAM_LANG_MAP:
        return _DEEPGRAM_LANG_MAP[code]
    return code


def _build_url(base_params: dict) -> str:
    """Construye URL con query params."""
    pairs = [f"{k}={v}" for k, v in base_params.items() if v is not None]
    return f"{DEEPGRAM_BASE}?{'&'.join(pairs)}"


async def _deepgram_request(url: str, audio_bytes: bytes) -> str:
    if not settings.DEEPGRAM_API_KEY:
        raise DeepgramError("DEEPGRAM_API_KEY no configurado")
    headers = {
        "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
    }
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    url,
                    headers=headers,
                    content=audio_bytes,
                )
            if resp.status_code != 200:
                detail = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
                raise DeepgramError(detail)
            return resp.text
        except (httpx.RequestError, DeepgramError) as exc:
            last_error = exc
            logger.warning(
                "Intento %d/2 Deepgram falló: %s", attempt + 1, type(exc).__name__,
            )
            if attempt == 0:
                await asyncio.sleep(1.0)
    raise DeepgramError(f"Deepgram falló tras 2 intentos: {last_error}")


def _parse_chunk_response(raw: str) -> str:
    """Extrae el transcript de una respuesta de Deepgram sin diarización."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise DeepgramError(f"Respuesta no JSON: {e}") from e
    try:
        alt = data["results"]["channels"][0]["alternatives"][0]
        return (alt.get("transcript") or "").strip()
    except (KeyError, IndexError) as e:
        raise DeepgramError(f"Estructura de respuesta inesperada: {e}") from e


def _parse_full_response(raw: str) -> str:
    """
    Extrae el transcript con etiquetas de hablante de una respuesta con
    diarización. Formato:
      Speaker 0: texto...
      Speaker 1: respuesta...
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise DeepgramError(f"Respuesta no JSON: {e}") from e
    try:
        alt = data["results"]["channels"][0]["alternatives"][0]
    except (KeyError, IndexError) as e:
        raise DeepgramError(f"Estructura de respuesta inesperada: {e}") from e

    # Preferir párrafos con speaker (diarización)
    paragraphs = (alt.get("paragraphs") or {}).get("paragraphs")
    if paragraphs:
        lines: list[str] = []
        for para in paragraphs:
            speaker = para.get("speaker", 0)
            sentences = para.get("sentences", [])
            text = " ".join(s.get("text", "") for s in sentences).strip()
            if text:
                lines.append(f"Speaker {speaker}: {text}")
        if lines:
            return "\n".join(lines)

    # Fallback: transcript plano sin diarización (aunque se pidió diarize=true)
    plain = (alt.get("transcript") or "").strip()
    return plain if plain else ""


async def transcribe_chunk_deepgram(audio_bytes: bytes, language: str) -> str:
    """Deepgram per‑chunk SIN diarización → texto plano (para live web)."""
    url = _build_url({
        "model": "nova-2",
        "language": _dg_lang(language),
        "smart_format": "true",
    })
    raw = await _deepgram_request(url, audio_bytes)
    return _parse_chunk_response(raw)


async def transcribe_full_deepgram(audio_bytes: bytes, language: str) -> str:
    """Deepgram audio completo CON diarización → Speaker 0/1 (desktop)."""
    url = _build_url({
        "model": "nova-2",
        "language": _dg_lang(language),
        "diarize": "true",
        "smart_format": "true",
        "punctuate": "true",
        "paragraphs": "true",
    })
    raw = await _deepgram_request(url, audio_bytes)
    return _parse_full_response(raw)
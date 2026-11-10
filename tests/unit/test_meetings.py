"""
Tests unitarios del módulo de Reuniones (transcripción, resumen y pipeline).

Siguen la convención del repo: unit puros con `pytest.mark.asyncio` y mocks
(sin fixtures de DB/ASGI). El fake de sesión distingue consultas por nombre
de tabla en el SQL generado.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from mind.meetings import service as meeting_service
import httpx

from mind.meetings import summarizer, transcriber
from mind.meetings.transcriber import TranscriptionError

# ---------------------------------------------------------------------------
# Fake de sesión async sin DB
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        if isinstance(self._value, list):
            return self._value[0] if len(self._value) >= 1 else None
        return self._value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return [self._value] if self._value is not None else []


class FakeSession:
    def __init__(self, meeting, chunks):
        self.meeting = meeting
        self.chunks = chunks
        self.commits = 0

    async def execute(self, stmt):
        text = str(stmt).upper().replace("\n", " ")
        if "FROM MEETING_AUDIO_CHUNKS" in text:
            return _FakeResult(self.chunks)
        if "FROM MEETINGS" in text:
            return _FakeResult(self.meeting)
        return _FakeResult(None)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


class _FakeFactory:
    """Reemplaza `_session_factory` por un async context manager de `FakeSession`."""

    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


def make_chunk(chunk_id=1, seq=1, data=b"audio", duration_ms=15000, transcribed=False, text=None):
    return SimpleNamespace(
        id=chunk_id, seq=seq, data=data, duration_ms=duration_ms,
        transcribed=transcribed, text=text,
    )


def make_meeting(status="processing", transcript=None, audio_format="webm", stt_provider="openrouter", diarize=False):
    return SimpleNamespace(
        id=1, status=status, transcript=transcript, summary=None,
        duration_seconds=None, finished_at=None, audio_format=audio_format,
        language="es", stt_provider=stt_provider, diarize=diarize,
        updated_at=None, error_message=None,
    )


@pytest.fixture(autouse=True)
def _session_patch():
    """Garantiza que el servicio nunca caiga en `_session_factory is None`."""
    original = meeting_service._session_factory
    meeting_service._session_factory = lambda: _FakeFactory(FakeSession(None, []))
    yield
    meeting_service._session_factory = original


# ---------------------------------------------------------------------------
# Transcripción
# ---------------------------------------------------------------------------


class TestAudioExtension:
    @pytest.mark.parametrize(
        "fmt,expected",
        [
            ("webm", "webm"),
            ("mp4", "m4a"),
            ("m4a", "m4a"),
            ("ogg", "ogg"),
            ("mp3", "mp3"),
            (None, "webm"),
            ("desconocido", "webm"),
        ],
    )
    def test_mapping(self, fmt, expected):
        assert transcriber.audio_extension(fmt) == expected


class TestTranscribeAudioRouter:
    """El router `transcribe_audio` despacha al proveedor correcto."""

    async def test_openrouter_route(self, monkeypatch):
        async def fake_or(*a, **kw):
            return "openrouter result"
        monkeypatch.setattr("mind.meetings.transcriber._transcribe_openrouter", fake_or)

        text = await transcriber.transcribe_audio(b"x", "webm", stt_provider="openrouter")
        assert text == "openrouter result"

    async def test_deepgram_chunk_route(self, monkeypatch):
        async def fake_chunk(audio, lang):
            return "deepgram chunk"
        monkeypatch.setattr(
            "mind.meetings.transcriber_deepgram.transcribe_chunk_deepgram", fake_chunk,
        )
        text = await transcriber.transcribe_audio(b"x", "wav", stt_provider="deepgram", diarize=False)
        assert text == "deepgram chunk"

    async def test_deepgram_full_route(self, monkeypatch):
        async def fake_full(audio, lang):
            return "Speaker 0: hola\nSpeaker 1: chau"
        monkeypatch.setattr(
            "mind.meetings.transcriber_deepgram.transcribe_full_deepgram", fake_full,
        )
        text = await transcriber.transcribe_audio(b"x", "wav", stt_provider="deepgram", diarize=True)
        assert text == "Speaker 0: hola\nSpeaker 1: chau"

    async def test_rejects_too_large_audio(self, monkeypatch):
        with pytest.raises(TranscriptionError):
            await transcriber.transcribe_audio(b"x" * (24 * 1024 * 1024 + 1), "wav")


class TestTranscribeDeepgram:
    """Tests del módulo Deepgram con httpx mockeado."""

    async def test_chunk_returns_plain_text(self, monkeypatch):
        async def fake_post(self, url, **kw):
            return SimpleNamespace(
                status_code=200,
                text='{"results":{"channels":[{"alternatives":[{"transcript":"texto de prueba"}]}]}}',
                json=lambda: {"results":{"channels":[{"alternatives":[{"transcript":"texto de prueba"}]}]}},
            )
        monkeypatch.setattr("mind.config.settings.DEEPGRAM_API_KEY", "fake-key")
        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        from mind.meetings.transcriber_deepgram import transcribe_chunk_deepgram
        text = await transcribe_chunk_deepgram(b"audio", "es")
        assert text == "texto de prueba"

    async def test_full_returns_speaker_labels(self, monkeypatch):
        async def fake_post(self, url, **kw):
            return SimpleNamespace(
                status_code=200,
                text='{"results":{"channels":[{"alternatives":[{"paragraphs":{"paragraphs":[{"speaker":0,"sentences":[{"text":"Hola"}]},{"speaker":1,"sentences":[{"text":"Chau"}]}]}}]}]}}',
                json=lambda: {"results":{"channels":[{"alternatives":[{"paragraphs":{"paragraphs":[{"speaker":0,"sentences":[{"text":"Hola"}]},{"speaker":1,"sentences":[{"text":"Chau"}]}]}}]}]}},
            )
        monkeypatch.setattr("mind.config.settings.DEEPGRAM_API_KEY", "fake-key")
        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        from mind.meetings.transcriber_deepgram import transcribe_full_deepgram
        text = await transcribe_full_deepgram(b"audio", "es")
        assert "Speaker 0" in text
        assert "Speaker 1" in text

    async def test_fails_without_key(self, monkeypatch):
        monkeypatch.setattr("mind.config.settings.DEEPGRAM_API_KEY", "")
        from mind.meetings.transcriber_deepgram import transcribe_chunk_deepgram, DeepgramError
        with pytest.raises(DeepgramError):
            await transcribe_chunk_deepgram(b"x", "es")


# ---------------------------------------------------------------------------
# Resumidor
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        text = '{"resumen_general": "resumen", "puntos_clave": ["a"], "decisiones": [], "tareas": []}'
        data = summarizer._extract_json(text)
        assert data["puntos_clave"] == ["a"]
        assert data["resumen_general"] == "resumen"

    def test_fenced_markdown(self):
        text = '```json\n{"resumen_general": "r", "puntos_clave": ["x"], "decisiones": [], "tareas": []}\n```'
        assert summarizer._extract_json(text)["puntos_clave"] == ["x"]

    def test_tolerates_surrounding_text(self):
        text = 'Aquí va el resumen: {"resumen_general": "r", "puntos_clave": ["y"], "decisiones": [], "tareas": [{"tarea": "t", "responsable": "r"}]}'
        data = summarizer._extract_json(text)
        assert data["puntos_clave"] == ["y"]
        assert data["tareas"] == [{"tarea": "t", "responsable": "r"}]

    def test_invalid_returns_empty(self):
        assert summarizer._extract_json("no json aquí")["puntos_clave"] == []

    def test_empty_returns_empty(self):
        assert summarizer._extract_json("") == {
            "resumen_general": "", "puntos_clave": [], "decisiones": [], "tareas": [],
        }


class TestGenerateSummary:
    async def test_empty_transcript_returns_empty(self):
        assert await summarizer.generate_summary("  ") == {
            "resumen_general": "", "puntos_clave": [], "decisiones": [], "tareas": [],
        }


# ---------------------------------------------------------------------------
# Pipeline (service)
# ---------------------------------------------------------------------------


class TestFinalizeMeeting:
    async def test_transcribes_pending_chunks_and_rebuilds(self, monkeypatch):
        """Los chunks pendientes se transcriben y el transcript se reconstruye
        desde chunk.text (en orden de seq), incluso con algunos ya transcritos."""
        meeting = make_meeting(status="processing")
        chunks = [
            make_chunk(chunk_id=10, seq=1, transcribed=True, text="primera parte"),
            make_chunk(chunk_id=11, seq=2, transcribed=False),
            make_chunk(chunk_id=12, seq=3, transcribed=False),
        ]
        session = FakeSession(meeting, chunks)
        meeting_service._session_factory = _FakeFactory(session)

        calls = {"n": 0}

        async def fake_transcribe(audio, fmt, language, stt_provider="openrouter", diarize=False):
            calls["n"] += 1
            return f"parte {calls['n']}"

        async def fake_summary(transcript):
            assert "primera parte" in transcript
            return {"puntos_clave": ["p"], "decisiones": [], "tareas": []}

        monkeypatch.setattr(meeting_service, "transcribe_audio", fake_transcribe)
        monkeypatch.setattr(summarizer, "generate_summary", fake_summary)

        await meeting_service.finalize_meeting(1)

        assert calls["n"] == 2  # solo pendientes
        assert meeting.status == "ready"
        assert meeting.transcript == "primera parte\nparte 1\nparte 2"
        assert meeting.duration_seconds == 45
        assert meeting.summary == {"puntos_clave": ["p"], "decisiones": [], "tareas": []}

    async def test_marks_error_when_all_chunks_fail(self, monkeypatch):
        meeting = make_meeting(status="processing")
        chunks = [make_chunk(chunk_id=10, seq=1, transcribed=False)]
        session = FakeSession(meeting, chunks)
        meeting_service._session_factory = _FakeFactory(session)

        async def boom(audio, fmt, language, stt_provider="openrouter", diarize=False):
            raise TranscriptionError("boom")

        monkeypatch.setattr(meeting_service, "transcribe_audio", boom)

        await meeting_service.finalize_meeting(1)

        assert meeting.status == "error"
        assert meeting.error_message

    async def test_partial_ready_when_some_chunks_fail(self, monkeypatch):
        meeting = make_meeting(status="processing")
        chunks = [
            make_chunk(chunk_id=10, seq=1, transcribed=False),
            make_chunk(chunk_id=11, seq=2, transcribed=False),
        ]
        session = FakeSession(meeting, chunks)
        meeting_service._session_factory = _FakeFactory(session)

        state = {"n": 0}

        async def fake_transcribe(audio, fmt, language, stt_provider="openrouter", diarize=False):
            state["n"] += 1
            if state["n"] == 1:
                raise TranscriptionError("boom chunk1")
            return "texto del chunk2"

        monkeypatch.setattr(meeting_service, "transcribe_audio", fake_transcribe)

        await meeting_service.finalize_meeting(1)

        assert meeting.status == "ready"
        assert meeting.transcript == "texto del chunk2"
        assert meeting.error_message

    async def test_marks_error_when_no_audio(self, monkeypatch):
        meeting = make_meeting(status="processing")
        session = FakeSession(meeting, [])
        meeting_service._session_factory = _FakeFactory(session)
        calls = {"n": 0}

        async def fake_transcribe(audio, fmt, language, stt_provider="openrouter", diarize=False):
            calls["n"] += 1
            return "x"

        monkeypatch.setattr(meeting_service, "transcribe_audio", fake_transcribe)

        await meeting_service.finalize_meeting(1)
        assert calls["n"] == 0
        assert meeting.status == "ready"
        assert meeting.error_message == "No se recibió audio"

    async def test_idempotent_on_ready_meeting(self, monkeypatch):
        meeting = make_meeting(status="ready", transcript="ya")
        session = FakeSession(meeting, [])
        meeting_service._session_factory = _FakeFactory(session)
        calls = {"n": 0}

        async def fake_transcribe(audio, fmt, language, stt_provider="openrouter", diarize=False):
            calls["n"] += 1
            return "x"

        monkeypatch.setattr(meeting_service, "transcribe_audio", fake_transcribe)

        await meeting_service.finalize_meeting(1)
        assert calls["n"] == 0
        assert meeting.status == "ready"


class TestTranscribeChunkTask:
    async def test_skips_when_meeting_not_recording(self, monkeypatch):
        """Si ya no está recording, no transcribe (lo hará finalize)."""
        meeting = make_meeting(status="processing")
        chunk = make_chunk(chunk_id=10, seq=1, transcribed=False)
        session = FakeSession(meeting, [chunk])
        meeting_service._session_factory = _FakeFactory(session)
        calls = {"n": 0}

        async def fake_transcribe(audio, fmt, language, stt_provider="openrouter", diarize=False):
            calls["n"] += 1
            return "x"

        monkeypatch.setattr(meeting_service, "transcribe_audio", fake_transcribe)

        await meeting_service.transcribe_chunk_task(1, 10)
        assert calls["n"] == 0
        assert chunk.transcribed is False

    async def test_transcribes_when_recording(self, monkeypatch):
        meeting = make_meeting(status="recording")
        chunk = make_chunk(chunk_id=10, seq=1, transcribed=False)
        session = FakeSession(meeting, [chunk])
        meeting_service._session_factory = _FakeFactory(session)

        async def fake_transcribe(audio, fmt, language, stt_provider="openrouter", diarize=False):
            return "frase grabada"

        monkeypatch.setattr(meeting_service, "transcribe_audio", fake_transcribe)

        await meeting_service.transcribe_chunk_task(1, 10)
        assert chunk.transcribed is True
        assert chunk.text == "frase grabada"


class TestSweepStaleMeetings:
    async def test_no_crash_without_meetings(self, monkeypatch):
        session = FakeSession(None, [])
        meeting_service._session_factory = _FakeFactory(session)
        await meeting_service.sweep_stale_meetings()
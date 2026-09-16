"""
Tests unitarios para mind/audit/logger.py.
Requisitos: 8.1, 8.7
"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest

from mind.audit.logger import (
    AuditRecord,
    MAX_ERROR_CHARS,
    MAX_REQUEST_CHARS,
    MAX_RESPONSE_CHARS,
    _truncate,
    _write_to_stderr,
    log_interaction,
    sanitize,
)


class TestAuditRecord:

    def test_request_content_truncated(self):
        record = AuditRecord(event_type="interaction", request_content="x" * (MAX_REQUEST_CHARS + 100))
        assert len(record.request_content) == MAX_REQUEST_CHARS

    def test_response_content_truncated(self):
        record = AuditRecord(event_type="interaction", response_content="y" * (MAX_RESPONSE_CHARS + 100))
        assert len(record.response_content) == MAX_RESPONSE_CHARS

    def test_error_description_truncated(self):
        record = AuditRecord(event_type="tool_failure", error_description="e" * (MAX_ERROR_CHARS + 100))
        assert len(record.error_description) == MAX_ERROR_CHARS

    def test_bearer_token_in_request_redacted(self):
        token = "A" * 30
        record = AuditRecord(event_type="interaction", request_content=f"Bearer {token}")
        assert token not in record.request_content
        assert "[REDACTED]" in record.request_content

    def test_tool_params_sanitized(self):
        secret = "sk-" + "x" * 30
        record = AuditRecord(event_type="tool_failure", tool_params={"api_key": secret, "n": 5})
        assert secret not in str(record.tool_params)


class TestLogInteraction:

    @pytest.mark.asyncio
    async def test_retries_3_times_then_writes_stderr(self, capsys):
        record = AuditRecord(event_type="interaction", chat_id=123, status="success")
        with patch("mind.audit.logger._write_record", new_callable=AsyncMock) as mock_write:
            mock_write.side_effect = Exception("DB error")
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await log_interaction(record)  # no debe lanzar
        assert mock_write.call_count == 3
        assert "[AUDIT_FAIL]" in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_succeeds_first_attempt(self):
        record = AuditRecord(event_type="interaction", chat_id=123, status="success")
        with patch("mind.audit.logger._write_record", new_callable=AsyncMock) as mock_write:
            await log_interaction(record)
        assert mock_write.call_count == 1

    @pytest.mark.asyncio
    async def test_succeeds_second_attempt(self):
        record = AuditRecord(event_type="interaction", chat_id=123)
        calls = 0

        async def fail_once(*a, **k):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise Exception("transient")

        with patch("mind.audit.logger._write_record", new_callable=AsyncMock) as mock_write:
            mock_write.side_effect = fail_once
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await log_interaction(record)
        assert mock_write.call_count == 2


class TestWriteToStderr:

    def test_writes_required_fields(self, capsys):
        _write_to_stderr("db timeout", "interaction")
        err = capsys.readouterr().err
        assert "[AUDIT_FAIL]" in err
        assert "interaction" in err
        assert "db timeout" in err
        assert "timestamp=" in err

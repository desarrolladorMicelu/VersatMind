"""
Property tests para sanitize() — Propiedad 20.
Valida: Requisitos 8.5, 8.6
"""
import re
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


class TestSanitizeProperty20:
    """Propiedad 20: sanitización reemplaza todos los secretos con [REDACTED]."""

    @given(st.text())
    @settings(max_examples=200)
    def test_no_bearer_tokens_after_sanitize(self, text: str):
        from mind.audit.logger import sanitize
        result = sanitize(text)
        # No debe quedar 'Bearer <token20+>' sin redactar
        matches = re.findall(r"Bearer\s+([A-Za-z0-9_\-]{20,})", result)
        for match in matches:
            assert match == "[REDACTED]"

    @given(st.text())
    @settings(max_examples=200)
    def test_no_sk_tokens_after_sanitize(self, text: str):
        from mind.audit.logger import sanitize
        result = sanitize(text)
        matches = re.findall(r"sk-([A-Za-z0-9_\-]{20,})", result)
        for match in matches:
            assert match == "[REDACTED]"

    @given(st.text())
    @settings(max_examples=200)
    def test_sanitize_is_idempotent(self, text: str):
        from mind.audit.logger import sanitize
        assert sanitize(sanitize(text)) == sanitize(text)

    def test_sanitize_redacts_known_bearer_token(self):
        from mind.audit.logger import sanitize
        token = "A" * 25
        result = sanitize(f"Authorization: Bearer {token}")
        assert token not in result
        assert "[REDACTED]" in result

    def test_sanitize_redacts_sk_key(self):
        from mind.audit.logger import sanitize
        key = "sk-" + "x" * 25
        result = sanitize(key)
        assert "x" * 25 not in result
        assert "[REDACTED]" in result

    def test_clean_text_unchanged(self):
        from mind.audit.logger import sanitize
        text = "Las ventas del mes fueron de 1000 unidades."
        assert sanitize(text) == text

    def test_short_bearer_not_redacted(self):
        from mind.audit.logger import sanitize
        # Token de menos de 20 chars no debe redactarse
        result = sanitize("Bearer short")
        assert "short" in result

"""
Property tests para validación de fechas — Propiedad 14.
Valida: Requisitos 5.1, 5.2, 5.4, 5.5
"""
from __future__ import annotations

import pytest
from datetime import date
from hypothesis import given, settings
from hypothesis import strategies as st

from mind.agent.tools.data_tools import validate_date_params


class TestDateValidationProperty14:
    """Propiedad 14: Herramientas de datos aceptan fechas ISO 8601 válidas y rechazan las inválidas."""

    @given(
        start=st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31)),
        end=st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31)),
    )
    @settings(max_examples=100)
    def test_valid_range_accepted(self, start: date, end: date):
        if start <= end:
            result = validate_date_params(start.isoformat(), end.isoformat())
            assert result.is_valid is True
        else:
            result = validate_date_params(start.isoformat(), end.isoformat())
            assert result.is_valid is False
            assert result.error_field == "fecha_fin"

    @given(st.text())
    @settings(max_examples=100)
    def test_invalid_format_always_rejected(self, text: str):
        """Cualquier texto que no sea fecha ISO 8601 válida es rechazado."""
        try:
            date.fromisoformat(text)
            is_date = True
        except (ValueError, TypeError):
            is_date = False

        if not is_date:
            result = validate_date_params(text, "2024-01-01")
            assert result.is_valid is False

    def test_end_before_start_rejected(self):
        result = validate_date_params("2024-06-01", "2024-01-01")
        assert result.is_valid is False
        assert result.error_field == "fecha_fin"

    def test_same_date_valid(self):
        result = validate_date_params("2024-03-15", "2024-03-15")
        assert result.is_valid is True

    def test_invalid_start_date(self):
        result = validate_date_params("not-a-date", "2024-01-01")
        assert result.is_valid is False
        assert result.error_field == "fecha_inicio"

    def test_invalid_end_date(self):
        result = validate_date_params("2024-01-01", "31-12-2024")
        assert result.is_valid is False
        assert result.error_field == "fecha_fin"

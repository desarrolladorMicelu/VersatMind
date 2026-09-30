"""
Tests del motor de prompts programados: cron, variables y render.
Valida mind/scheduler/prompts.py.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from mind.scheduler.prompts import (
    available_variables,
    build_context,
    compose_cron,
    render_prompt,
)


class TestComposeCron:

    def test_daily(self):
        assert compose_cron("daily", hour=8, minute=0) == "0 8 * * *"

    def test_daily_with_minutes(self):
        assert compose_cron("daily", hour=7, minute=30) == "30 7 * * *"

    def test_weekly_uses_weekday_name(self):
        # 0 = lunes
        assert compose_cron("weekly", hour=9, minute=15, weekday=0) == "15 9 * * mon"

    def test_weekly_sunday(self):
        assert compose_cron("weekly", hour=9, minute=0, weekday=6) == "0 9 * * sun"

    def test_custom_passthrough(self):
        assert compose_cron("custom", custom="*/5 * * * *") == "*/5 * * * *"

    def test_custom_requires_expression(self):
        with pytest.raises(ValueError):
            compose_cron("custom", custom="")

    def test_hour_and_minute_clamped(self):
        assert compose_cron("daily", hour=99, minute=99) == "59 23 * * *"


class TestRenderPrompt:

    def test_replaces_known_variables(self):
        out = render_prompt("Ventas de {{ayer}} en {{tienda}}", {"ayer": "2026-09-29", "tienda": "MICELU"})
        assert out == "Ventas de 2026-09-29 en MICELU"

    def test_unknown_variable_left_intact(self):
        out = render_prompt("Hola {{desconocida}}", {"fecha": "2026-09-30"})
        assert out == "Hola {{desconocida}}"

    def test_tolerates_spaces(self):
        assert render_prompt("{{  fecha  }}", {"fecha": "2026-09-30"}) == "2026-09-30"

    def test_empty_template(self):
        assert render_prompt("", {"fecha": "x"}) == ""


class TestBuildContext:

    def test_context_fields(self):
        tz = ZoneInfo("America/Bogota")
        now = datetime(2026, 9, 30, 8, 5, tzinfo=tz)  # miércoles
        ctx = build_context(SimpleNamespace(name="MICELU"), now=now)
        assert ctx["fecha"] == "2026-09-30"
        assert ctx["ayer"] == "2026-09-29"
        assert ctx["manana"] == "2026-10-01"
        assert ctx["inicio_mes"] == "2026-09-01"
        assert ctx["inicio_semana"] == "2026-09-28"  # lunes
        assert ctx["dia_semana"] == "miércoles"
        assert ctx["hora"] == "08:05"
        assert ctx["tienda"] == "MICELU"

    def test_available_variables_not_empty(self):
        keys = {v["key"] for v in available_variables()}
        assert {"fecha", "ayer", "tienda", "inicio_mes"}.issubset(keys)

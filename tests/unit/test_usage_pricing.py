"""
Tests para el cálculo de costos de consumo de tokens.

Valida mind/usage/pricing.py y los límites de período de mind/usage/tracker.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from hypothesis import given, settings as hsettings
from hypothesis import strategies as st

from mind.usage.pricing import (
    DEFAULT_PRICING,
    compute_cost_usd,
    get_pricing,
    normalize_model,
)
from mind.usage.tracker import period_bounds


class TestNormalizeModel:

    def test_strips_provider_prefix(self):
        assert normalize_model("openai/gpt-4o-mini") == "gpt-4o-mini"

    def test_lowercases(self):
        assert normalize_model("OpenAI/GPT-4O") == "gpt-4o"

    def test_handles_none_and_empty(self):
        assert normalize_model(None) == ""
        assert normalize_model("") == ""


class TestGetPricing:

    def test_known_model(self):
        assert get_pricing("gpt-4o-mini") == (0.15, 0.60)

    def test_prefix_match_prefers_longest(self):
        # "gpt-4.1-mini" debe ganar a "gpt-4.1"
        assert get_pricing("openai/gpt-4.1-mini") == (0.40, 1.60)

    def test_unknown_model_uses_default(self):
        assert get_pricing("modelo-inexistente-xyz") == DEFAULT_PRICING


class TestComputeCostUsd:

    def test_cost_for_known_model(self):
        # 1M input @0.15 + 1M output @0.60 = 0.75
        assert compute_cost_usd("openai/gpt-4o-mini", 1_000_000, 1_000_000) == 0.75

    def test_zero_tokens(self):
        assert compute_cost_usd("gpt-4o", 0, 0) == 0.0

    def test_negative_tokens_clamped(self):
        assert compute_cost_usd("gpt-4o", -5, -5) == 0.0

    @given(
        model=st.sampled_from(["openai/gpt-4o-mini", "gpt-4o", "desconocido"]),
        prompt=st.integers(min_value=0, max_value=1_000_000),
        completion=st.integers(min_value=0, max_value=1_000_000),
    )
    @hsettings(max_examples=50)
    def test_cost_is_non_negative(self, model: str, prompt: int, completion: int):
        assert compute_cost_usd(model, prompt, completion) >= 0.0


class TestPeriodBounds:

    def test_month_period(self):
        now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
        start, key, label = period_bounds("month", now)
        assert start == datetime(2026, 9, 1, tzinfo=timezone.utc)
        assert key == "2026-09"
        assert "2026-09" in label

    def test_total_period(self):
        start, key, _ = period_bounds("total", datetime(2026, 9, 30, tzinfo=timezone.utc))
        assert start is None
        assert key == "total"

"""Tests for Step 4.3 — cost & model accounting."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from data_compass.config import FX_USD_TO_GBP, MODEL_HAIKU, MODEL_SONNET
from data_compass.core.costing import CostLine, build_cost_line, compute_cost


def _usage(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation: int = 0,
    cache_read: int = 0,
) -> MagicMock:
    u = MagicMock()
    u.input_tokens = input_tokens
    u.output_tokens = output_tokens
    u.cache_creation_input_tokens = cache_creation
    u.cache_read_input_tokens = cache_read
    return u


class TestComputeCost:
    def test_sonnet_input_only(self):
        # 1M input tokens at £3/MTok × FX
        u = _usage(input_tokens=1_000_000)
        cost = compute_cost(u, MODEL_SONNET)
        assert abs(cost - 3.00 * FX_USD_TO_GBP) < 1e-6

    def test_haiku_output_only(self):
        # 1M output tokens at £5/MTok × FX
        u = _usage(output_tokens=1_000_000)
        cost = compute_cost(u, MODEL_HAIKU)
        assert abs(cost - 5.00 * FX_USD_TO_GBP) < 1e-6

    def test_cache_read_at_tenth_of_input_rate(self):
        # 1M cache-read tokens at 0.1 × Sonnet input rate × FX
        u = _usage(cache_read=1_000_000)
        cost = compute_cost(u, MODEL_SONNET)
        assert abs(cost - 3.00 * 0.1 * FX_USD_TO_GBP) < 1e-6

    def test_none_usage_returns_zero(self):
        assert compute_cost(None, MODEL_SONNET) == 0.0

    def test_unknown_model_returns_zero(self):
        assert compute_cost(_usage(input_tokens=1000), "claude-unknown-99") == 0.0

    def test_small_realistic_call(self):
        # ~500 input + 80 output tokens with Sonnet — should be tiny but non-zero
        u = _usage(input_tokens=500, output_tokens=80)
        cost = compute_cost(u, MODEL_SONNET)
        assert cost > 0.0
        assert cost < 0.01  # less than a penny


class TestBuildCostLine:
    def test_empty_list_gives_no_ai_cost_line(self):
        cl = build_cost_line([])
        assert cl.cost_gbp == 0.0
        assert cl.models == []
        assert "No AI used" in cl.label

    def test_single_model_label(self):
        u = _usage(input_tokens=100, output_tokens=20)
        cl = build_cost_line([(MODEL_SONNET, u)])
        assert "Sonnet" in cl.label
        assert "£" in cl.label

    def test_two_models_label(self):
        u1 = _usage(input_tokens=200)
        u2 = _usage(output_tokens=50)
        cl = build_cost_line([(MODEL_SONNET, u1), (MODEL_HAIKU, u2)])
        assert "Sonnet" in cl.label
        assert "Haiku" in cl.label
        assert "+" in cl.label

    def test_cost_is_sum_of_individual_costs(self):
        u1 = _usage(input_tokens=500_000)
        u2 = _usage(output_tokens=100_000)
        cl = build_cost_line([(MODEL_SONNET, u1), (MODEL_HAIKU, u2)])
        expected = compute_cost(u1, MODEL_SONNET) + compute_cost(u2, MODEL_HAIKU)
        assert abs(cl.cost_gbp - expected) < 1e-9

    def test_none_usage_skipped_in_model_list(self):
        cl = build_cost_line([(MODEL_SONNET, None)])
        assert cl.models == []


class TestCostLineLabel:
    def test_label_includes_four_decimal_places(self):
        cl = CostLine(models=["claude-sonnet-4-6"], cost_gbp=0.00123456)
        assert "0.0012" in cl.label

    def test_no_ai_label_shows_zero(self):
        cl = CostLine()
        assert "£0.0000" in cl.label

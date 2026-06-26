"""Tests for Step 5.4 — Tier 3 Haiku adjudication (API fully mocked)."""
from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock

import numpy as np
import pytest

from data_compass.cache.adjudicate import adjudicate
from data_compass.cache.store import Template
from data_compass.config import CACHE_THRESHOLD, MODEL_HAIKU


def _template(tid: int, question: str, sql: str, param_defs=None) -> Template:
    return Template(
        id=tid, dataset_id="land_registry", scope="public", exact_key=f"k{tid}",
        question=question, sql_template=sql, param_defs=param_defs or [],
        embedding=np.array([0.1, 0.2], dtype=np.float32),
        created_at="2026-01-01T00:00:00+00:00",
    )


def _response(payload_text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=payload_text)]
    resp.usage = MagicMock(input_tokens=150, output_tokens=30)
    return resp


_CANDIDATES = [
    _template(1, "How many sales per county?",
              "SELECT county, COUNT(*) FROM properties GROUP BY county"),
    _template(
        2, "Sales above a price?",
        "SELECT * FROM transactions WHERE price > {min_price}",
        param_defs=[{"name": "min_price", "type": "int"}],
    ),
]


class TestMatch:
    def test_high_confidence_match_returns_template(self):
        payload = '{"match_index": 1, "confidence": 0.95, "params": {}}'
        with mock.patch("data_compass.cache.adjudicate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            result = adjudicate("sk-ant-test", "Count of sales by county", _CANDIDATES)
        assert result.matched is True
        assert result.template.id == 1
        assert result.confidence == pytest.approx(0.95)
        assert result.usage is not None

    def test_match_extracts_params(self):
        payload = '{"match_index": 2, "confidence": 0.9, "params": {"min_price": 500000}}'
        with mock.patch("data_compass.cache.adjudicate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            result = adjudicate("sk-ant-test", "Sales over 500k?", _CANDIDATES)
        assert result.matched is True
        assert result.template.id == 2
        assert result.params == {"min_price": 500000}

    def test_uses_haiku(self):
        payload = '{"match_index": 1, "confidence": 0.9, "params": {}}'
        with mock.patch("data_compass.cache.adjudicate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            adjudicate("sk-ant-test", "q", _CANDIDATES)
            kwargs = MockC.return_value.messages.create.call_args.kwargs
        assert kwargs["model"] == MODEL_HAIKU

    def test_json_embedded_in_prose_is_parsed(self):
        payload = 'Here is my answer:\n{"match_index": 1, "confidence": 0.88, "params": {}}\nDone.'
        with mock.patch("data_compass.cache.adjudicate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            result = adjudicate("sk-ant-test", "q", _CANDIDATES)
        assert result.matched is True


class TestStrictPrompt:
    """The adjudicator must instruct Haiku to require structural equivalence,
    so 'by county' is not matched to 'by county and town'."""

    def test_system_prompt_demands_structural_match(self):
        payload = '{"match_index": null, "confidence": 0.0, "params": {}}'
        with mock.patch("data_compass.cache.adjudicate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            adjudicate("sk-ant-test", "average price by county", _CANDIDATES)
            system = MockC.return_value.messages.create.call_args.kwargs["system"]
        low = system.lower()
        assert "grouping" in low
        assert "not a match" in low or "must not match" in low
        # Only parameter VALUES may differ — the key precision rule.
        assert "parameter" in low


class TestMiss:
    def test_below_threshold_is_miss(self):
        low = CACHE_THRESHOLD - 0.2
        payload = f'{{"match_index": 1, "confidence": {low}, "params": {{}}}}'
        with mock.patch("data_compass.cache.adjudicate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            result = adjudicate("sk-ant-test", "q", _CANDIDATES)
        assert result.matched is False
        assert result.template is None

    def test_null_match_index_is_miss(self):
        payload = '{"match_index": null, "confidence": 0.0, "params": {}}'
        with mock.patch("data_compass.cache.adjudicate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            result = adjudicate("sk-ant-test", "Totally unrelated question", _CANDIDATES)
        assert result.matched is False

    def test_out_of_range_index_is_miss(self):
        payload = '{"match_index": 9, "confidence": 0.99, "params": {}}'
        with mock.patch("data_compass.cache.adjudicate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            result = adjudicate("sk-ant-test", "q", _CANDIDATES)
        assert result.matched is False

    def test_unparseable_response_is_miss(self):
        with mock.patch("data_compass.cache.adjudicate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response("no json here")
            result = adjudicate("sk-ant-test", "q", _CANDIDATES)
        assert result.matched is False

    def test_empty_candidates_makes_no_api_call(self):
        with mock.patch("data_compass.cache.adjudicate.anthropic.Anthropic") as MockC:
            result = adjudicate("sk-ant-test", "q", [])
        MockC.assert_not_called()
        assert result.matched is False

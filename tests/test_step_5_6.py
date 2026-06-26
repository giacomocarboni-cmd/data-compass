"""
Phase 5 completion test — tiered cache wired into the app.

User journey: ask a question (miss → Sonnet generates + stores a template),
then ask the same question again (Tier-1 exact hit → no API calls, zero cost,
same SQL). The Anthropic SDK is mocked at the lowest level; the local embedder
is replaced with a fake vector; DuckDB execution is real.
"""
from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from data_compass.cache import store
from data_compass.config import MODEL_SONNET
from data_compass.i18n import t

_TEMPLATE_SQL = (
    "SELECT p.county, COUNT(*) AS sales "
    "FROM transactions t JOIN properties p ON t.property_id = p.property_id "
    "GROUP BY p.county ORDER BY sales DESC LIMIT 5"
)

_GEN_PAYLOAD = (
    '{"sql_template": "' + _TEMPLATE_SQL + '", "param_defs": [], "params": {}}'
)

_QUESTION = "How many sales per county?"


def _usage(inp=400, out=80):
    u = MagicMock()
    u.input_tokens = inp
    u.output_tokens = out
    u.cache_creation_input_tokens = 0
    u.cache_read_input_tokens = 0
    return u


def _sdk_response(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = _usage()
    return resp


def _fake_embed(texts):
    return np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)


def _ask(at, question: str):
    """Navigate (idempotent) and submit a question on an already-run app."""
    key_input = next(
        ti for ti in at.text_input
        if "api" in ti.label.lower() or "key" in ti.label.lower()
    )
    at = key_input.set_value("sk-ant-test").run()
    at.text_area[0].set_value(question).run()
    return at.button[0].click().run()


@pytest.fixture
def shared_cache():
    c = store.connect(":memory:")
    yield c
    c.close()


def _run_pipeline(shared_cache, questions: list[str]) -> tuple[AppTest, list]:
    """Run a sequence of questions through the app on one shared cache.

    Returns the final AppTest and the list of QueryResults (one per question).
    """
    # generate (Sonnet) and summary (Haiku) share the same anthropic.Anthropic
    # symbol, so route a single mocked client by the requested model.
    def _create(*args, model=None, **kwargs):
        if model == MODEL_SONNET:
            return _sdk_response(_GEN_PAYLOAD)
        return _sdk_response("Greater London leads on sales.")

    client = MagicMock()
    client.messages.create.side_effect = _create

    results = []
    with (
        mock.patch("data_compass.cache.resource.get_cache_conn", return_value=shared_cache),
        mock.patch("data_compass.cache.generate.embed_question", side_effect=lambda q, embed_fn=None: _fake_embed([q])[0]),
        mock.patch("anthropic.Anthropic", return_value=client),
    ):
        at = AppTest.from_file("app.py", default_timeout=60).run()
        picker = next(sb for sb in at.selectbox if "dataset" in sb.label.lower() or "Demo" in sb.label)
        at = picker.select("UK Property Sales 2024").run()
        at.radio[0].set_value(t("app.nav.query")).run()

        for q in questions:
            at = _ask(at, q)
            results.append(at.session_state["query_result"])

    return at, results


class TestTieredCacheJourney:
    def test_first_query_is_a_miss_and_stores_template(self, shared_cache):
        _, results = _run_pipeline(shared_cache, [_QUESTION])
        first = results[0]
        assert first.error is None
        assert first.cache_tier == "miss"
        assert store.count_templates(shared_cache) == 1

    def test_repeat_query_is_exact_cache_hit(self, shared_cache):
        _, results = _run_pipeline(shared_cache, [_QUESTION, _QUESTION])
        miss, hit = results
        assert miss.cache_tier == "miss"
        assert hit.cache_tier == "exact"
        # No new template created on the hit
        assert store.count_templates(shared_cache) == 1

    def test_cache_hit_costs_nothing(self, shared_cache):
        _, results = _run_pipeline(shared_cache, [_QUESTION, _QUESTION])
        hit = results[1]
        assert hit.cost_line.cost_gbp == 0.0
        assert hit.cost_line.models == []
        assert "No AI used" in hit.cost_line.label

    def test_cache_hit_reuses_same_sql(self, shared_cache):
        _, results = _run_pipeline(shared_cache, [_QUESTION, _QUESTION])
        assert results[0].sql == results[1].sql == _TEMPLATE_SQL

    def test_cache_hit_reuses_summary_without_api(self, shared_cache):
        _, results = _run_pipeline(shared_cache, [_QUESTION, _QUESTION])
        # Same summary text, but the hit made no summary API call
        assert results[1].summary == results[0].summary

    def test_miss_cost_line_shows_models(self, shared_cache):
        _, results = _run_pipeline(shared_cache, [_QUESTION])
        miss = results[0]
        assert miss.cost_line.cost_gbp > 0.0
        assert "Sonnet" in miss.cost_line.label

    def test_hit_caption_rendered_in_ui(self, shared_cache):
        at, _ = _run_pipeline(shared_cache, [_QUESTION, _QUESTION])
        captions = " ".join(c.value for c in at.caption)
        assert "No AI used" in captions
        assert t("query.cache_exact") in captions

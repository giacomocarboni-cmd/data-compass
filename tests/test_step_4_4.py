"""
Phase 4 integration tests — Results panel (table + chart + summary + cost).

Anthropic API fully mocked. DuckDB execution is real (uses bundled CSVs).
"""
from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from data_compass.cache import store
from data_compass.cache.generate import GenerationResult
from data_compass.i18n import t

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_SQL = (
    "SELECT p.county, COUNT(*) AS sales, ROUND(AVG(t.price)) AS avg_price "
    "FROM transactions t "
    "JOIN properties p ON t.property_id = p.property_id "
    "GROUP BY p.county ORDER BY sales DESC LIMIT 5"
)

_MOCK_SUMMARY = "Greater London led with the most property sales in 2024."


def _make_sql_usage():
    u = MagicMock()
    u.input_tokens = 500
    u.output_tokens = 60
    u.cache_creation_input_tokens = 0
    u.cache_read_input_tokens = 0
    return u


def _make_summary_usage():
    u = MagicMock()
    u.input_tokens = 120
    u.output_tokens = 40
    u.cache_creation_input_tokens = 0
    u.cache_read_input_tokens = 0
    return u


def _gen_result(sql: str = _MOCK_SQL) -> GenerationResult:
    return GenerationResult(sql=sql, stored=False, usage=_make_sql_usage())


def _run_full_query(question: str = "How many sales per county?") -> AppTest:
    """Run a full query with a fresh in-memory cache; Tier-4 generation and the
    summary call are mocked (no live API)."""
    with (
        mock.patch(
            "data_compass.cache.resource.get_cache_conn",
            return_value=store.connect(":memory:"),
        ),
        mock.patch(
            "data_compass.core.query_flow.generate_and_store",
            return_value=_gen_result(),
        ),
        mock.patch(
            "data_compass.core.query_flow.generate_summary",
            return_value=(_MOCK_SUMMARY, _make_summary_usage()),
        ),
    ):
        at = AppTest.from_file("app.py", default_timeout=30).run()

        picker = next(
            sb for sb in at.selectbox
            if "dataset" in sb.label.lower() or "Demo" in sb.label
        )
        at = picker.select("UK Property Sales 2024").run()
        at.radio[0].set_value(t("app.nav.query")).run()

        key_input = next(
            ti for ti in at.text_input
            if "api" in ti.label.lower() or "key" in ti.label.lower()
        )
        at = key_input.set_value("sk-ant-test-key").run()
        at.text_area[0].set_value(question).run()
        at = at.button[0].click().run()

    return at


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestResultsPanel:
    def test_result_table_rendered(self):
        at = _run_full_query()
        assert len(at.dataframe) >= 1

    def test_sql_code_block_rendered(self):
        at = _run_full_query()
        code_blocks = [c.value for c in at.code]
        assert any(_MOCK_SQL in block for block in code_blocks)

    def test_chart_subheader_rendered(self):
        at = _run_full_query()
        headers = " ".join(h.value for h in list(at.subheader))
        assert t("query.chart_header") in headers

    def test_summary_rendered(self):
        at = _run_full_query()
        all_text = " ".join(m.value for m in at.markdown)
        assert _MOCK_SUMMARY in all_text

    def test_cost_caption_rendered(self):
        at = _run_full_query()
        captions = " ".join(c.value for c in at.caption)
        assert "£" in captions

    def test_cost_caption_shows_sonnet_and_haiku(self):
        at = _run_full_query()
        captions = " ".join(c.value for c in at.caption)
        assert "Sonnet" in captions
        assert "Haiku" in captions

    def test_results_subheader_present(self):
        at = _run_full_query()
        headers = " ".join(h.value for h in list(at.subheader))
        assert t("query.results_header") in headers

    def test_sql_subheader_present(self):
        at = _run_full_query()
        headers = " ".join(h.value for h in list(at.subheader))
        assert t("query.sql_header") in headers


class TestResultsWithEmptyResult:
    def test_no_rows_info_shown(self):
        empty_sql = "SELECT * FROM transactions WHERE 1=0"
        with (
            mock.patch(
                "data_compass.cache.resource.get_cache_conn",
                return_value=store.connect(":memory:"),
            ),
            mock.patch(
                "data_compass.core.query_flow.generate_and_store",
                return_value=_gen_result(sql=empty_sql),
            ),
            mock.patch(
                "data_compass.core.query_flow.generate_summary",
                return_value=(None, None),
            ),
        ):
            at = AppTest.from_file("app.py", default_timeout=30).run()
            picker = next(sb for sb in at.selectbox if "dataset" in sb.label.lower() or "Demo" in sb.label)
            at = picker.select("UK Property Sales 2024").run()
            at.radio[0].set_value(t("app.nav.query")).run()
            key_input = next(ti for ti in at.text_input if "api" in ti.label.lower() or "key" in ti.label.lower())
            at = key_input.set_value("sk-ant-test").run()
            at.text_area[0].set_value("zero rows please").run()
            at = at.button[0].click().run()

        info_text = " ".join(i.value for i in at.info)
        assert "no rows" in info_text.lower() or "returned" in info_text.lower()

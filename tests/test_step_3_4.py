"""
Unit tests for Step 3.4 — Query flow & UI (SQL + table).

The Anthropic API is fully mocked — no live calls, no spend.
The guard and DuckDB execution run against the real bundled data.
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


def _make_usage():
    u = MagicMock()
    u.input_tokens = 200
    u.output_tokens = 45
    u.cache_creation_input_tokens = 0
    u.cache_read_input_tokens = 0
    return u


def _gen_result(sql: str = _MOCK_SQL, error: str | None = None) -> GenerationResult:
    return GenerationResult(sql=sql, stored=False, error=error, usage=_make_usage())


def _app() -> AppTest:
    return AppTest.from_file("app.py", default_timeout=30)


def _run_with_mock(question: str = "How many sales per county?"):
    """
    Run the app with a fresh in-memory cache (so Tier 4 generation runs) and a
    mocked generate_and_store + generate_summary. Select Land Registry, go to
    Query, enter an API key, type a question, and click Ask.
    """
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
            return_value=("Mocked summary.", _make_usage()),
        ),
    ):
        at = _app().run()

        # Select dataset
        picker = next(
            sb for sb in at.selectbox
            if "dataset" in sb.label.lower() or "Demo" in sb.label
        )
        at = picker.select("UK Property Sales 2024").run()

        # Navigate to Query
        at.radio[0].set_value(t("app.nav.query")).run()

        # Enter API key
        key_input = next(
            ti for ti in at.text_input
            if "api" in ti.label.lower() or "key" in ti.label.lower()
        )
        at = key_input.set_value("sk-ant-test-key").run()

        # Enter question and click Ask
        at.text_area[0].set_value(question).run()
        at = at.button[0].click().run()

    return at


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestQueryPanelGating:
    def test_no_dataset_shows_warning(self):
        at = _app().run()
        at.radio[0].set_value(t("app.nav.query")).run()
        at = at.run()
        warnings = " ".join(w.value for w in at.warning)
        assert "dataset" in warnings.lower() or "select" in warnings.lower()

    def test_no_api_key_shows_warning(self):
        at = _app().run()
        picker = next(sb for sb in at.selectbox if "dataset" in sb.label.lower() or "Demo" in sb.label)
        at = picker.select("UK Property Sales 2024").run()
        at.radio[0].set_value(t("app.nav.query")).run()
        at = at.run()
        warnings = " ".join(w.value for w in at.warning)
        assert "key" in warnings.lower() or "api" in warnings.lower()


class TestQueryFlow:
    def test_sql_block_rendered_after_ask(self):
        at = _run_with_mock()
        code_blocks = [c.value for c in at.code]
        assert any(_MOCK_SQL in block for block in code_blocks)

    def test_result_dataframe_rendered(self):
        at = _run_with_mock()
        assert len(at.dataframe) >= 1

    def test_sql_header_present(self):
        at = _run_with_mock()
        headers = " ".join(h.value for h in list(at.subheader))
        assert t("query.sql_header") in headers or "SQL" in headers

    def test_results_header_present(self):
        at = _run_with_mock()
        headers = " ".join(h.value for h in list(at.subheader))
        assert t("query.results_header") in headers or "Results" in headers


class TestSafetyGate:
    def test_unsafe_sql_shows_error(self):
        with (
            mock.patch(
                "data_compass.cache.resource.get_cache_conn",
                return_value=store.connect(":memory:"),
            ),
            mock.patch(
                "data_compass.core.query_flow.generate_and_store",
                return_value=_gen_result(sql="DELETE FROM transactions", error="unsafe"),
            ),
            mock.patch(
                "data_compass.core.query_flow.generate_summary",
                return_value=(None, None),
            ),
        ):
            at = _app().run()
            picker = next(sb for sb in at.selectbox if "dataset" in sb.label.lower() or "Demo" in sb.label)
            at = picker.select("UK Property Sales 2024").run()
            at.radio[0].set_value(t("app.nav.query")).run()
            key_input = next(ti for ti in at.text_input if "api" in ti.label.lower() or "key" in ti.label.lower())
            at = key_input.set_value("sk-ant-test").run()
            at.text_area[0].set_value("delete everything").run()
            at = at.button[0].click().run()

        errors = " ".join(e.value for e in at.error)
        assert "safe" in errors.lower() or "blocked" in errors.lower()

"""Tests for Step 5.5 — Tier 4 Sonnet generate + store (API mocked, DuckDB real)."""
from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock

import numpy as np
import pytest

from data_compass.cache import store
from data_compass.cache.generate import generate_and_store, substitute
from data_compass.config import MODEL_SONNET
from data_compass.data.loader import load_dataset


@pytest.fixture
def cache_conn():
    c = store.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def duck_conn():
    conn = load_dataset("land_registry")
    yield conn
    conn.close()


def _fake_embed(texts):
    return np.array([[0.1, 0.2, 0.3]], dtype=np.float32)


def _response(payload_text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=payload_text)]
    resp.usage = MagicMock(input_tokens=400, output_tokens=80)
    return resp


class TestSubstitute:
    def test_numeric_substitution(self):
        assert substitute("price > {min_price}", {"min_price": 500000}) == "price > 500000"

    def test_string_substitution(self):
        assert substitute("county = '{county}'", {"county": "Hampshire"}) == "county = 'Hampshire'"

    def test_missing_param_left_untouched(self):
        assert substitute("x = {y}", {}) == "x = {y}"

    def test_no_placeholders(self):
        assert substitute("SELECT 1", {}) == "SELECT 1"


class TestGenerateAndStore:
    def test_valid_sql_is_stored_with_embedding(self, cache_conn, duck_conn):
        payload = (
            '{"sql_template": "SELECT county, COUNT(*) AS n FROM properties '
            'GROUP BY county", "param_defs": [], "params": {}}'
        )
        with mock.patch("data_compass.cache.generate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            result = generate_and_store(
                "sk-ant-test", cache_conn, duck_conn,
                "How many sales per county?", "land_registry", "<schema>",
                embed_fn=_fake_embed,
            )
        assert result.stored is True
        assert result.template_id is not None
        assert result.error is None
        # Template persisted with an embedding
        tmpl = store.get_by_exact_key(cache_conn, "land_registry", "how many sales per county")
        assert tmpl is not None
        assert tmpl.embedding is not None
        assert store.count_templates(cache_conn) == 1

    def test_parameterised_sql_substituted_and_stored(self, cache_conn, duck_conn):
        payload = (
            '{"sql_template": "SELECT * FROM transactions WHERE price > {min_price} LIMIT 5", '
            '"param_defs": [{"name": "min_price", "type": "int"}], '
            '"params": {"min_price": 100000}}'
        )
        with mock.patch("data_compass.cache.generate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            result = generate_and_store(
                "sk-ant-test", cache_conn, duck_conn,
                "Show sales over 100k", "land_registry", "<schema>",
                embed_fn=_fake_embed,
            )
        assert result.stored is True
        assert result.sql == "SELECT * FROM transactions WHERE price > 100000 LIMIT 5"
        tmpl = store.get_by_exact_key(cache_conn, "land_registry", "show sales over 100k")
        assert "{min_price}" in tmpl.sql_template  # template keeps the placeholder
        assert tmpl.param_defs == [{"name": "min_price", "type": "int"}]

    def test_unsafe_sql_not_stored(self, cache_conn, duck_conn):
        payload = '{"sql_template": "DELETE FROM transactions", "param_defs": [], "params": {}}'
        with mock.patch("data_compass.cache.generate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            result = generate_and_store(
                "sk-ant-test", cache_conn, duck_conn,
                "delete it all", "land_registry", "<schema>",
                embed_fn=_fake_embed,
            )
        assert result.stored is False
        assert result.error == "unsafe"
        assert store.count_templates(cache_conn) == 0

    def test_invalid_sql_not_stored(self, cache_conn, duck_conn):
        payload = (
            '{"sql_template": "SELECT nonexistent_col FROM no_such_table", '
            '"param_defs": [], "params": {}}'
        )
        with mock.patch("data_compass.cache.generate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            result = generate_and_store(
                "sk-ant-test", cache_conn, duck_conn,
                "broken query", "land_registry", "<schema>",
                embed_fn=_fake_embed,
            )
        assert result.stored is False
        assert result.error is not None
        assert store.count_templates(cache_conn) == 0

    def test_unparseable_response_returns_error(self, cache_conn, duck_conn):
        with mock.patch("data_compass.cache.generate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response("not json at all")
            result = generate_and_store(
                "sk-ant-test", cache_conn, duck_conn,
                "q", "land_registry", "<schema>", embed_fn=_fake_embed,
            )
        assert result.stored is False
        assert result.error is not None
        assert store.count_templates(cache_conn) == 0

    def test_uses_sonnet(self, cache_conn, duck_conn):
        payload = '{"sql_template": "SELECT 1", "param_defs": [], "params": {}}'
        with mock.patch("data_compass.cache.generate.anthropic.Anthropic") as MockC:
            MockC.return_value.messages.create.return_value = _response(payload)
            generate_and_store(
                "sk-ant-test", cache_conn, duck_conn,
                "q", "land_registry", "<schema>", embed_fn=_fake_embed,
            )
            kwargs = MockC.return_value.messages.create.call_args.kwargs
        assert kwargs["model"] == MODEL_SONNET

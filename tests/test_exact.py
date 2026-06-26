"""Tests for Step 5.2 — Tier 1 exact/normalised match."""
from __future__ import annotations

import pytest

from data_compass.cache import store
from data_compass.cache.exact import lookup_exact, normalise


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    store.insert_template(
        c,
        dataset_id="land_registry",
        exact_key=normalise("How many sales per county?"),
        question="How many sales per county?",
        sql_template="SELECT county, COUNT(*) FROM properties GROUP BY county",
    )
    yield c
    c.close()


class TestNormalise:
    def test_lowercases(self):
        assert normalise("HELLO World") == "hello world"

    def test_strips_trailing_question_mark(self):
        assert normalise("how many?") == "how many"

    def test_collapses_internal_whitespace(self):
        assert normalise("how   many    sales") == "how many sales"

    def test_strips_outer_whitespace(self):
        assert normalise("  hello  ") == "hello"

    def test_strips_surrounding_quotes(self):
        assert normalise('"hello"') == "hello"

    def test_combined(self):
        assert normalise('  "How   MANY sales?" ') == "how many sales"


class TestLookupExact:
    def test_exact_repeat_hits(self, conn):
        tmpl = lookup_exact(conn, "land_registry", "How many sales per county?")
        assert tmpl is not None
        assert "GROUP BY county" in tmpl.sql_template

    def test_case_and_punctuation_variation_hits(self, conn):
        tmpl = lookup_exact(conn, "land_registry", "  how many SALES per county  ")
        assert tmpl is not None

    def test_whitespace_variation_hits(self, conn):
        tmpl = lookup_exact(conn, "land_registry", "How many sales   per county?")
        assert tmpl is not None

    def test_different_question_misses(self, conn):
        assert lookup_exact(conn, "land_registry", "What is the average price?") is None

    def test_different_dataset_misses(self, conn):
        assert lookup_exact(conn, "uk_weather", "How many sales per county?") is None

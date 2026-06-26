"""Tests for Step 5.1 — cache store schema and round-trip."""
from __future__ import annotations

import numpy as np
import pytest

from data_compass.cache import store


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


class TestRoundTrip:
    def test_insert_then_fetch_by_exact_key(self, conn):
        tid = store.insert_template(
            conn,
            dataset_id="land_registry",
            exact_key="how many sales per county",
            question="How many sales per county?",
            sql_template="SELECT county, COUNT(*) FROM properties GROUP BY county",
        )
        assert tid > 0

        tmpl = store.get_by_exact_key(conn, "land_registry", "how many sales per county")
        assert tmpl is not None
        assert tmpl.id == tid
        assert tmpl.question == "How many sales per county?"
        assert "GROUP BY county" in tmpl.sql_template
        assert tmpl.param_defs == []
        assert tmpl.scope == "public"

    def test_param_defs_round_trip(self, conn):
        params = [{"name": "min_price", "type": "int", "default": 100000}]
        store.insert_template(
            conn,
            dataset_id="land_registry",
            exact_key="sales above price",
            question="Sales above a price?",
            sql_template="SELECT * FROM transactions WHERE price > {min_price}",
            param_defs=params,
        )
        tmpl = store.get_by_exact_key(conn, "land_registry", "sales above price")
        assert tmpl.param_defs == params

    def test_embedding_round_trip(self, conn):
        vec = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        store.insert_template(
            conn,
            dataset_id="uk_weather",
            exact_key="rainfall by year",
            question="Rainfall by year?",
            sql_template="SELECT year, SUM(rain_mm) FROM observations GROUP BY year",
            embedding=vec,
        )
        tmpl = store.get_by_exact_key(conn, "uk_weather", "rainfall by year")
        assert tmpl.embedding is not None
        np.testing.assert_allclose(tmpl.embedding, vec, rtol=1e-6)


class TestMissAndScope:
    def test_unknown_key_returns_none(self, conn):
        assert store.get_by_exact_key(conn, "land_registry", "nonexistent") is None

    def test_dataset_scoping(self, conn):
        store.insert_template(
            conn, dataset_id="land_registry", exact_key="k",
            question="q", sql_template="SELECT 1",
        )
        # Same key, different dataset → miss
        assert store.get_by_exact_key(conn, "uk_weather", "k") is None

    def test_login_scope_isolation(self, conn):
        store.insert_template(
            conn, dataset_id="land_registry", exact_key="k",
            question="q", sql_template="SELECT 1", scope="user-42",
        )
        # Public scope cannot see a user-scoped template
        assert store.get_by_exact_key(conn, "land_registry", "k", scope="public") is None
        assert store.get_by_exact_key(conn, "land_registry", "k", scope="user-42") is not None


class TestDatasetListing:
    def test_get_templates_for_dataset(self, conn):
        for i in range(3):
            store.insert_template(
                conn, dataset_id="land_registry", exact_key=f"k{i}",
                question=f"q{i}", sql_template="SELECT 1",
            )
        store.insert_template(
            conn, dataset_id="uk_weather", exact_key="w",
            question="w", sql_template="SELECT 1",
        )
        lr = store.get_templates_for_dataset(conn, "land_registry")
        assert len(lr) == 3
        assert all(t.dataset_id == "land_registry" for t in lr)

    def test_count_templates(self, conn):
        assert store.count_templates(conn) == 0
        store.insert_template(
            conn, dataset_id="land_registry", exact_key="k",
            question="q", sql_template="SELECT 1",
        )
        assert store.count_templates(conn) == 1


class TestEmbeddingHelpers:
    def test_encode_decode_none(self):
        assert store.encode_embedding(None) is None
        assert store.decode_embedding(None) is None

    def test_encode_decode_round_trip(self):
        vec = np.array([1.5, -2.0, 3.25], dtype=np.float32)
        blob = store.encode_embedding(vec)
        assert isinstance(blob, bytes)
        out = store.decode_embedding(blob)
        np.testing.assert_allclose(out, vec, rtol=1e-6)


class TestPersistence:
    def test_file_backed_persists_across_connections(self, tmp_path):
        db = tmp_path / "nested" / "cache.db"
        c1 = store.connect(db)
        store.insert_template(
            c1, dataset_id="land_registry", exact_key="k",
            question="q", sql_template="SELECT 1",
        )
        c1.close()

        c2 = store.connect(db)
        assert store.get_by_exact_key(c2, "land_registry", "k") is not None
        c2.close()

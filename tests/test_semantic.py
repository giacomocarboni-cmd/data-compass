"""
Tests for Step 5.3 — Tier 2 FAISS semantic retrieval.

Embeddings are supplied deterministically (no model download) for retrieval
logic. One opt-in test exercises the real local embedder (zero API cost) to
prove a paraphrase retrieves the correct template.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from data_compass.cache import store
from data_compass.cache.semantic import embed_question, retrieve


def _make_template(tid: int, vec: list[float], question: str = "q") -> store.Template:
    return store.Template(
        id=tid,
        dataset_id="land_registry",
        scope="public",
        exact_key=f"k{tid}",
        question=question,
        sql_template="SELECT 1",
        param_defs=[],
        embedding=np.array(vec, dtype=np.float32),
        created_at="2026-01-01T00:00:00+00:00",
    )


class TestRetrieve:
    def test_returns_closest_first(self):
        templates = [
            _make_template(1, [1.0, 0.0]),
            _make_template(2, [0.0, 1.0]),
            _make_template(3, [0.9, 0.1]),
        ]
        query = np.array([1.0, 0.0], dtype=np.float32)
        # Floor disabled here to assert pure ordering across all candidates.
        results = retrieve(query, templates, top_k=3, min_similarity=0.0)
        assert len(results) == 3
        # template 1 is an exact direction match → highest score
        assert results[0][0].id == 1
        # scores in descending order
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_filters_candidates_below_min_similarity(self):
        templates = [
            _make_template(1, [1.0, 0.0]),   # cosine 1.0 — kept
            _make_template(2, [0.0, 1.0]),   # cosine 0.0 — below floor, dropped
        ]
        query = np.array([1.0, 0.0], dtype=np.float32)
        results = retrieve(query, templates, top_k=3, min_similarity=0.5)
        assert [t.id for t, _ in results] == [1]

    def test_default_floor_drops_unrelated(self):
        # An orthogonal template (cosine 0.0) is below the default floor.
        templates = [_make_template(1, [0.0, 1.0])]
        query = np.array([1.0, 0.0], dtype=np.float32)
        assert retrieve(query, templates) == []

    def test_respects_top_k(self):
        templates = [_make_template(i, [float(i), 1.0]) for i in range(1, 6)]
        query = np.array([1.0, 1.0], dtype=np.float32)
        results = retrieve(query, templates, top_k=2)
        assert len(results) == 2

    def test_cosine_ignores_magnitude(self):
        # Same direction, very different magnitude → near-perfect similarity
        templates = [_make_template(1, [10.0, 0.0])]
        query = np.array([1.0, 0.0], dtype=np.float32)
        results = retrieve(query, templates, top_k=1)
        assert results[0][1] == pytest.approx(1.0, abs=1e-5)

    def test_skips_templates_without_embedding(self):
        t = _make_template(1, [1.0, 0.0])
        t_no_emb = store.Template(
            id=2, dataset_id="land_registry", scope="public", exact_key="k2",
            question="q", sql_template="SELECT 1", param_defs=[], embedding=None,
            created_at="2026-01-01T00:00:00+00:00",
        )
        query = np.array([1.0, 0.0], dtype=np.float32)
        results = retrieve(query, [t, t_no_emb], top_k=5)
        assert len(results) == 1
        assert results[0][0].id == 1

    def test_empty_candidates_returns_empty(self):
        query = np.array([1.0, 0.0], dtype=np.float32)
        assert retrieve(query, [], top_k=3) == []


class TestEmbedQuestion:
    def test_uses_injected_embed_fn(self):
        captured = {}

        def fake_embed(texts):
            captured["texts"] = texts
            return np.array([[0.1, 0.2, 0.3]], dtype=np.float32)

        vec = embed_question("hello", embed_fn=fake_embed)
        assert captured["texts"] == ["hello"]
        assert vec.shape == (3,)
        np.testing.assert_allclose(vec, [0.1, 0.2, 0.3], rtol=1e-6)


@pytest.mark.skipif(
    os.getenv("RUN_MODEL_TESTS") != "1",
    reason="set RUN_MODEL_TESTS=1 to run the real local-embedder test (downloads model)",
)
class TestRealEmbedderParaphrase:
    def test_paraphrase_retrieves_correct_template(self):
        from data_compass.cache.semantic import _default_embed

        questions = [
            "How many property sales were there in each county?",
            "What is the average rainfall by year?",
        ]
        templates = [
            _make_template(1, list(_default_embed([questions[0]])[0]), questions[0]),
            _make_template(2, list(_default_embed([questions[1]])[0]), questions[1]),
        ]
        paraphrase = "Count of house sales per county"
        query = embed_question(paraphrase)
        results = retrieve(query, templates, top_k=2)
        assert results[0][0].id == 1

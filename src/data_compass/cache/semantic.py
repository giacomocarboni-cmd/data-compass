"""
Tier 2 — FAISS semantic retrieval — Phase 5, Step 5.3.

Embeds the question locally (sentence-transformers, zero API cost) and
retrieves the top-K most similar stored templates via a FAISS inner-product
index over L2-normalised vectors (i.e. cosine similarity).

The embedding function is injectable (``embed_fn``) so tests can supply
deterministic vectors without downloading the model. In production the
default lazily loads and caches the configured model.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Callable

import faiss
import numpy as np

from data_compass.cache.store import Template
from data_compass.config import CACHE_MIN_SIMILARITY, CACHE_TOP_K, EMBEDDING_MODEL

EmbedFn = Callable[[list[str]], np.ndarray]


@lru_cache(maxsize=1)
def _get_model():
    """Lazily load and cache the sentence-transformers model."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


def _default_embed(texts: list[str]) -> np.ndarray:
    """Embed a list of texts with the configured local model."""
    model = _get_model()
    return np.asarray(model.encode(texts), dtype=np.float32)


def embed_question(question: str, *, embed_fn: EmbedFn | None = None) -> np.ndarray:
    """Return a 1-D float32 embedding for a single question."""
    fn = embed_fn or _default_embed
    vec = fn([question])
    return np.asarray(vec, dtype=np.float32).reshape(-1)


def _normalise_rows(mat: np.ndarray) -> np.ndarray:
    """L2-normalise each row; zero rows are left as zero."""
    mat = np.asarray(mat, dtype=np.float32)
    if mat.ndim == 1:
        mat = mat.reshape(1, -1)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def retrieve(
    query_vec: np.ndarray,
    templates: list[Template],
    *,
    top_k: int = CACHE_TOP_K,
    min_similarity: float = CACHE_MIN_SIMILARITY,
) -> list[tuple[Template, float]]:
    """Return up to ``top_k`` (template, cosine_similarity) pairs, best first.

    Templates without an embedding are skipped, and candidates scoring below
    ``min_similarity`` are dropped so clearly-unrelated templates never reach
    the (paid) adjudication step. Returns an empty list when there are no
    embeddable candidates above the floor.
    """
    candidates = [t for t in templates if t.embedding is not None]
    if not candidates:
        return []

    matrix = np.vstack([t.embedding for t in candidates]).astype(np.float32)
    matrix = _normalise_rows(matrix)

    query = _normalise_rows(query_vec.reshape(1, -1))

    dim = matrix.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(matrix)

    k = min(top_k, len(candidates))
    scores, idxs = index.search(query, k)

    results: list[tuple[Template, float]] = []
    for score, idx in zip(scores[0], idxs[0]):
        if idx < 0:
            continue
        if float(score) < min_similarity:
            continue  # too dissimilar to be a real match
        results.append((candidates[idx], float(score)))
    return results

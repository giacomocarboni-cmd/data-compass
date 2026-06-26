"""
Tier 1 — exact / normalised match — Phase 5, Step 5.2.

The cheapest tier: normalise the question to a canonical key and do a direct
SQLite lookup. A hit costs zero API tokens.

Normalisation (deliberately conservative — we only collapse trivial surface
variation, never meaning):
  - lower-case
  - strip leading/trailing whitespace
  - collapse internal whitespace runs to a single space
  - drop trailing punctuation (?, ., !) and surrounding quotes
"""
from __future__ import annotations

import re
import sqlite3

from data_compass.cache.store import Template, get_by_exact_key

_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_PUNCT_RE = re.compile(r"[?.!]+$")


def normalise(question: str) -> str:
    """Return the canonical exact-match key for a question."""
    q = question.strip().lower()
    q = q.strip("\"'")
    q = _WHITESPACE_RE.sub(" ", q)
    q = _TRAILING_PUNCT_RE.sub("", q).strip()
    return q


def lookup_exact(
    conn: sqlite3.Connection,
    dataset_id: str,
    question: str,
    *,
    scope: str = "public",
) -> Template | None:
    """Return a cached template for an exact/normalised match, or None."""
    key = normalise(question)
    return get_by_exact_key(conn, dataset_id, key, scope=scope)

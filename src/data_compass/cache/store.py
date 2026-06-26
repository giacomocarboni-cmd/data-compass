"""
Cache store — Phase 5, Step 5.1.

A SQLite-backed store of parameterised SQL templates. The cache stores
*templates* (parameterised SQL + parameter definitions), never result sets,
so data changes are always reflected when the template is re-executed.

Schema (one table, ``templates``):
  id              INTEGER PK
  dataset_id      TEXT     — registry id; scopes a template to its dataset
  scope           TEXT     — login scope ('public' or a user id); isolates
                            uploaded-dataset templates from the shared demo cache
  exact_key       TEXT     — normalised question, for Tier-1 exact lookup
  question        TEXT     — the original natural-language question
  sql_template    TEXT     — parameterised SQL ({param} placeholders)
  param_defs      TEXT     — JSON list of parameter definitions
  embedding       BLOB     — float32 sentence embedding (Tier-2 FAISS retrieval)
  summary         TEXT     — cached NL summary, reused on an exact (Tier-1) hit
  created_at      TEXT     — ISO-8601 UTC timestamp

Embeddings are stored as raw float32 bytes; use ``encode_embedding`` /
``decode_embedding`` to round-trip a numpy array.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

_SCHEMA = """
CREATE TABLE IF NOT EXISTS templates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id    TEXT NOT NULL,
    scope         TEXT NOT NULL DEFAULT 'public',
    exact_key     TEXT NOT NULL,
    question      TEXT NOT NULL,
    sql_template  TEXT NOT NULL,
    param_defs    TEXT NOT NULL DEFAULT '[]',
    embedding     BLOB,
    summary       TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_templates_lookup
    ON templates (dataset_id, scope, exact_key);
"""


@dataclass
class Template:
    """A stored, reusable SQL template."""
    id: int
    dataset_id: str
    scope: str
    exact_key: str
    question: str
    sql_template: str
    param_defs: list[dict[str, Any]]
    embedding: np.ndarray | None
    created_at: str
    summary: str | None = None


# ---------------------------------------------------------------------------
# Embedding (de)serialisation
# ---------------------------------------------------------------------------

def encode_embedding(vec: np.ndarray | None) -> bytes | None:
    """Serialise a 1-D float32 embedding to raw bytes (None → None)."""
    if vec is None:
        return None
    return np.asarray(vec, dtype=np.float32).tobytes()


def decode_embedding(blob: bytes | None) -> np.ndarray | None:
    """Deserialise raw bytes back to a 1-D float32 array (None → None)."""
    if blob is None:
        return None
    return np.frombuffer(blob, dtype=np.float32)


# ---------------------------------------------------------------------------
# Connection / schema
# ---------------------------------------------------------------------------

def connect(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open (and initialise) a cache database.

    Pass ``:memory:`` for an ephemeral in-process store (used in tests).
    A file path's parent directory is created if needed.
    """
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: Streamlit may re-run scripts on different threads
    # while sharing the cached connection; access is serialised by the GIL here.
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def insert_template(
    conn: sqlite3.Connection,
    *,
    dataset_id: str,
    exact_key: str,
    question: str,
    sql_template: str,
    param_defs: list[dict[str, Any]] | None = None,
    embedding: np.ndarray | None = None,
    scope: str = "public",
) -> int:
    """Insert a new template and return its row id."""
    created_at = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO templates
            (dataset_id, scope, exact_key, question, sql_template,
             param_defs, embedding, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_id,
            scope,
            exact_key,
            question,
            sql_template,
            json.dumps(param_defs or []),
            encode_embedding(embedding),
            created_at,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _row_to_template(row: sqlite3.Row) -> Template:
    return Template(
        id=row["id"],
        dataset_id=row["dataset_id"],
        scope=row["scope"],
        exact_key=row["exact_key"],
        question=row["question"],
        sql_template=row["sql_template"],
        param_defs=json.loads(row["param_defs"]),
        embedding=decode_embedding(row["embedding"]),
        created_at=row["created_at"],
        summary=row["summary"],
    )


def get_by_exact_key(
    conn: sqlite3.Connection,
    dataset_id: str,
    exact_key: str,
    *,
    scope: str = "public",
) -> Template | None:
    """Return the most recent template matching the exact key, or None."""
    row = conn.execute(
        """
        SELECT * FROM templates
        WHERE dataset_id = ? AND scope = ? AND exact_key = ?
        ORDER BY id DESC LIMIT 1
        """,
        (dataset_id, scope, exact_key),
    ).fetchone()
    return _row_to_template(row) if row else None


def get_templates_for_dataset(
    conn: sqlite3.Connection,
    dataset_id: str,
    *,
    scope: str = "public",
) -> list[Template]:
    """Return all templates for a dataset/scope (for FAISS index building)."""
    rows = conn.execute(
        "SELECT * FROM templates WHERE dataset_id = ? AND scope = ? ORDER BY id",
        (dataset_id, scope),
    ).fetchall()
    return [_row_to_template(r) for r in rows]


def set_summary(conn: sqlite3.Connection, template_id: int, summary: str | None) -> None:
    """Backfill the cached NL summary for a template (reused on exact hits)."""
    conn.execute(
        "UPDATE templates SET summary = ? WHERE id = ?",
        (summary, template_id),
    )
    conn.commit()


def delete_templates_for_scope(
    conn: sqlite3.Connection,
    dataset_id: str,
    scope: str,
) -> int:
    """Delete all cached templates for a dataset/scope; return the row count.

    Used by the GDPR consent-withdrawal "forget" path (Step 8.4) to drop any
    derived cached results for a user's uploaded data.
    """
    cur = conn.execute(
        "DELETE FROM templates WHERE dataset_id = ? AND scope = ?",
        (dataset_id, scope),
    )
    conn.commit()
    return cur.rowcount


def count_templates(conn: sqlite3.Connection) -> int:
    """Return the total number of stored templates (test/diagnostic helper)."""
    return int(conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0])

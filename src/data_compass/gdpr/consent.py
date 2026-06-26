"""
Town/Postcode retain-with-consent — Phase 8, Step 8.4.

By default the PII failsafe (Step 8.2) masks UK postcodes (and Town/Postcode
columns) in uploaded data. Geographic analysis is often the whole point of an
upload, so a *logged-in* user may opt in to **retain** Town/Postcode instead.
Because that is a deliberate choice to keep borderline-personal geographic
data, it is recorded as durable consent with a withdrawal path.

Scope decision (owner, 2026-06-22): consent applies to **uploaded data only**.
The bundled demo datasets are OGL public data about properties/places, not
living individuals, so they need no consent.

Records live in the shared SQLite auth DB (uploads are logged-in only, so every
consenter is identifiable). The table is append-only for accountability: a
grant inserts an active row; a withdrawal marks the active row(s) withdrawn
(``active = 0``, ``withdrawn_at`` set) without deleting the history. The
re-masking of retained columns and dropping of derived cache entries on
withdrawal is performed by the caller (the upload flow); this module owns the
durable consent record.

Schema (table ``consent_records``):
  id           INTEGER PK
  subject      TEXT — per-user identity (key_router.get_upload_scope)
  scope        TEXT — what the consent covers (default 'town_postcode')
  granted_at   TEXT — ISO-8601 UTC
  withdrawn_at TEXT — ISO-8601 UTC, NULL while active
  active       INTEGER — 1 = consent in force, 0 = withdrawn

Public API
----------
DEFAULT_SCOPE   str ('town_postcode')
ConsentRecord   dataclass
ensure_schema(conn)
grant_consent(conn, subject, scope=DEFAULT_SCOPE, *, now=None) -> ConsentRecord
withdraw_consent(conn, subject, scope=DEFAULT_SCOPE, *, now=None) -> bool
has_consent(conn, subject, scope=DEFAULT_SCOPE) -> bool
get_consent(conn, subject, scope=DEFAULT_SCOPE) -> ConsentRecord | None
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

DEFAULT_SCOPE = "town_postcode"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS consent_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject      TEXT NOT NULL,
    scope        TEXT NOT NULL,
    granted_at   TEXT NOT NULL,
    withdrawn_at TEXT,
    active       INTEGER NOT NULL DEFAULT 1
);
"""


@dataclass
class ConsentRecord:
    """One consent decision (granted, possibly later withdrawn)."""
    id: int
    subject: str
    scope: str
    granted_at: str
    withdrawn_at: str | None
    active: bool


def _now(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now


def _row_to_record(row: sqlite3.Row | None) -> ConsentRecord | None:
    if row is None:
        return None
    return ConsentRecord(
        id=row["id"],
        subject=row["subject"],
        scope=row["scope"],
        granted_at=row["granted_at"],
        withdrawn_at=row["withdrawn_at"],
        active=bool(row["active"]),
    )


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the consent_records table if absent (shares the auth DB)."""
    conn.executescript(_SCHEMA)
    conn.commit()


def grant_consent(
    conn: sqlite3.Connection,
    subject: str,
    scope: str = DEFAULT_SCOPE,
    *,
    now: datetime | None = None,
) -> ConsentRecord:
    """Record an active consent for ``subject``/``scope``.

    Any prior active consent for the same subject/scope is superseded so there
    is a single record in force; the superseded row is marked withdrawn rather
    than deleted, preserving the trail.
    """
    ensure_schema(conn)
    moment = _now(now).isoformat()
    # Supersede any currently-active grant for this subject/scope.
    conn.execute(
        """
        UPDATE consent_records SET active = 0, withdrawn_at = ?
        WHERE subject = ? AND scope = ? AND active = 1
        """,
        (moment, subject, scope),
    )
    cur = conn.execute(
        """
        INSERT INTO consent_records (subject, scope, granted_at, withdrawn_at, active)
        VALUES (?, ?, ?, NULL, 1)
        """,
        (subject, scope, moment),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM consent_records WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _row_to_record(row)


def withdraw_consent(
    conn: sqlite3.Connection,
    subject: str,
    scope: str = DEFAULT_SCOPE,
    *,
    now: datetime | None = None,
) -> bool:
    """Withdraw active consent for ``subject``/``scope``.

    Returns True if a consent was in force and is now withdrawn, else False.
    The caller is responsible for re-masking retained data and dropping any
    derived cache entries.
    """
    ensure_schema(conn)
    moment = _now(now).isoformat()
    cur = conn.execute(
        """
        UPDATE consent_records SET active = 0, withdrawn_at = ?
        WHERE subject = ? AND scope = ? AND active = 1
        """,
        (moment, subject, scope),
    )
    conn.commit()
    return cur.rowcount > 0


def get_consent(
    conn: sqlite3.Connection,
    subject: str,
    scope: str = DEFAULT_SCOPE,
) -> ConsentRecord | None:
    """Return the most recent consent record for ``subject``/``scope``."""
    ensure_schema(conn)
    row = conn.execute(
        """
        SELECT * FROM consent_records
        WHERE subject = ? AND scope = ?
        ORDER BY id DESC LIMIT 1
        """,
        (subject, scope),
    ).fetchone()
    return _row_to_record(row)


def has_consent(
    conn: sqlite3.Connection,
    subject: str,
    scope: str = DEFAULT_SCOPE,
) -> bool:
    """Return True if an active consent is in force for ``subject``/``scope``."""
    ensure_schema(conn)
    row = conn.execute(
        """
        SELECT 1 FROM consent_records
        WHERE subject = ? AND scope = ? AND active = 1
        LIMIT 1
        """,
        (subject, scope),
    ).fetchone()
    return row is not None

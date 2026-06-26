"""
Recruiter temporary logins — Phase 6, Step 6.3.

A recruiter is granted a single-use-style access token (not a username/password)
that is valid for a limited time and a limited number of queries. Defaults:
``RECRUITER_QUERY_CAP`` queries within ``RECRUITER_VALIDITY_DAYS`` days.

Token format
------------
``"<id>.<secret>"`` — the ``<id>`` locates the row (Argon2 hashes are salted and
cannot be looked up by value); the ``<secret>`` is verified against the stored
hash. The plaintext token is shown to the owner exactly once, at creation.

Gating is evaluated lazily on each use: a token is usable only while it is
``active`` AND ``now < expires_at`` AND ``queries_used < query_cap``. The 30-day
expiry blocks access even if queries remain, and the query cap blocks access even
if time remains.

Schema (table ``recruiter_tokens``):
  id            INTEGER PK
  token_hash    TEXT    — Argon2id hash of the secret half (never plaintext)
  label         TEXT    — human label, e.g. "Acme Corp – Jane"
  created_at    TEXT    — ISO-8601 UTC
  expires_at    TEXT    — ISO-8601 UTC
  query_cap     INTEGER — maximum queries allowed
  queries_used  INTEGER — running count, incremented on each query
  active        INTEGER — 1 = enabled, 0 = revoked
"""
from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from data_compass.auth.store import hash_password, verify_password
from data_compass.config import RECRUITER_QUERY_CAP, RECRUITER_VALIDITY_DAYS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recruiter_tokens (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash    TEXT NOT NULL,
    label         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    query_cap     INTEGER NOT NULL,
    queries_used  INTEGER NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1
);
"""


@dataclass
class RecruiterToken:
    """A stored recruiter access token (the hash is held, never displayed)."""
    id: int
    token_hash: str
    label: str
    created_at: str
    expires_at: str
    query_cap: int
    queries_used: int
    active: bool


@dataclass
class AccessResult:
    """Outcome of an access check for a recruiter token."""
    allowed: bool
    reason: str  # 'ok' | 'inactive' | 'expired' | 'quota_exceeded'
    remaining: int = 0


def _now(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now


def _parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the recruiter_tokens table if absent (shares the auth DB)."""
    conn.executescript(_SCHEMA)
    conn.commit()


def _row_to_token(row: sqlite3.Row | None) -> RecruiterToken | None:
    if row is None:
        return None
    return RecruiterToken(
        id=row["id"],
        token_hash=row["token_hash"],
        label=row["label"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        query_cap=row["query_cap"],
        queries_used=row["queries_used"],
        active=bool(row["active"]),
    )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def create_recruiter_token(
    conn: sqlite3.Connection,
    label: str = "",
    *,
    cap: int = RECRUITER_QUERY_CAP,
    days: int = RECRUITER_VALIDITY_DAYS,
    now: datetime | None = None,
) -> str:
    """Create a recruiter token and return the plaintext ``"<id>.<secret>"``.

    The plaintext is returned once and never recoverable thereafter.
    """
    ensure_schema(conn)
    now = _now(now)
    expires_at = now + timedelta(days=days)
    secret = secrets.token_urlsafe(24)
    cur = conn.execute(
        """
        INSERT INTO recruiter_tokens
            (token_hash, label, created_at, expires_at, query_cap, queries_used, active)
        VALUES (?, ?, ?, ?, ?, 0, 1)
        """,
        (hash_password(secret), label, now.isoformat(), expires_at.isoformat(), cap),
    )
    conn.commit()
    token_id = int(cur.lastrowid)
    return f"{token_id}.{secret}"


# ---------------------------------------------------------------------------
# Verification & access gating
# ---------------------------------------------------------------------------

def _split(token: str) -> tuple[int, str] | None:
    if not token or "." not in token:
        return None
    id_part, _, secret = token.partition(".")
    if not id_part.isdigit() or not secret:
        return None
    return int(id_part), secret


def get_token(conn: sqlite3.Connection, token_id: int) -> RecruiterToken | None:
    """Return the token row by id, or None."""
    row = conn.execute(
        "SELECT * FROM recruiter_tokens WHERE id = ?", (token_id,)
    ).fetchone()
    return _row_to_token(row)


def verify_token(conn: sqlite3.Connection, token: str) -> RecruiterToken | None:
    """Return the token row if the secret is valid (authentication only).

    Does *not* check expiry or quota — use ``check_access`` for gating.
    """
    parsed = _split(token)
    if parsed is None:
        return None
    token_id, secret = parsed
    row = get_token(conn, token_id)
    if row is None:
        return None
    if not verify_password(row.token_hash, secret):
        return None
    return row


def check_access(
    token: RecruiterToken, *, now: datetime | None = None
) -> AccessResult:
    """Evaluate whether a (already-authenticated) token may run a query now."""
    now = _now(now)
    remaining = max(0, token.query_cap - token.queries_used)
    if not token.active:
        return AccessResult(False, "inactive", remaining)
    if now >= _parse_ts(token.expires_at):
        return AccessResult(False, "expired", remaining)
    if token.queries_used >= token.query_cap:
        return AccessResult(False, "quota_exceeded", 0)
    return AccessResult(True, "ok", remaining)


# ---------------------------------------------------------------------------
# Usage & administration
# ---------------------------------------------------------------------------

def increment_usage(conn: sqlite3.Connection, token_id: int) -> int:
    """Increment the query counter and return the new ``queries_used`` value."""
    conn.execute(
        "UPDATE recruiter_tokens SET queries_used = queries_used + 1 WHERE id = ?",
        (token_id,),
    )
    conn.commit()
    row = get_token(conn, token_id)
    return row.queries_used if row else 0


def deactivate(conn: sqlite3.Connection, token_id: int) -> None:
    """Revoke a token immediately, regardless of remaining quota/time."""
    conn.execute(
        "UPDATE recruiter_tokens SET active = 0 WHERE id = ?", (token_id,)
    )
    conn.commit()

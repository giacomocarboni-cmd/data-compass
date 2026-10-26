"""
Auth store & password hashing — Phase 6, Step 6.1.

A SQLite-backed store of user accounts (admins). Passwords are hashed with
Argon2id via ``argon2-cffi``; the plaintext is never stored, logged, or
returned. Recruiter temporary logins live in a separate table managed by
``auth.recruiter`` (Step 6.3).

Schema (one table, ``users``):
  id              INTEGER PK
  username        TEXT UNIQUE  — login name
  password_hash   TEXT         — Argon2id PHC-format hash (never plaintext)
  role            TEXT         — 'admin' (recruiters are tokens, not users)
  password_set_at TEXT         — ISO-8601 UTC; drives the renewal policy (6.2)
  created_at      TEXT         — ISO-8601 UTC

The admin account is seeded once from the environment via ``seed_admin``.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'admin',
    password_set_at TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
"""

# A single shared hasher (default Argon2id parameters are sensible for a
# low-traffic portfolio app; tuning is a deploy-time concern).
_hasher = PasswordHasher()


@dataclass
class User:
    """A stored user account (the hash is held but never displayed)."""
    id: int
    username: str
    password_hash: str
    role: str
    password_set_at: str
    created_at: str


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return an Argon2id PHC-format hash of ``password``."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Return True if ``password`` matches ``password_hash`` (never raises)."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------------------
# Connection / schema
# ---------------------------------------------------------------------------

def connect(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open (and initialise) the auth database.

    Pass ``:memory:`` for an ephemeral in-process store (used in tests).
    A file path's parent directory is created if needed.
    """
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _row_to_user(row: sqlite3.Row | None) -> User | None:
    if row is None:
        return None
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        role=row["role"],
        password_set_at=row["password_set_at"],
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def create_user(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    *,
    role: str = "admin",
) -> int:
    """Create a user with a hashed password; return the new row id.

    Raises ``sqlite3.IntegrityError`` if the username already exists.
    """
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO users (username, password_hash, role, password_set_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (username, hash_password(password), role, now, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def set_password(conn: sqlite3.Connection, user_id: int, new_password: str) -> None:
    """Replace a user's password hash and reset ``password_set_at`` to now."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE users SET password_hash = ?, password_set_at = ? WHERE id = ?",
        (hash_password(new_password), now, user_id),
    )
    conn.commit()


def seed_admin(conn: sqlite3.Connection, username: str, password: str) -> bool:
    """Seed the admin account on first run.

    Idempotent: creates the admin only if no user with ``username`` exists.
    Returns True if the admin was created, False if it already existed.
    A blank password is refused (returns False without creating anything).
    """
    if not password or not password.strip():
        return False
    if get_user(conn, username) is not None:
        return False
    create_user(conn, username, password, role="admin")
    return True


# ---------------------------------------------------------------------------
# Reads / authentication
# ---------------------------------------------------------------------------

def get_user(conn: sqlite3.Connection, username: str) -> User | None:
    """Return the user with this username, or None."""
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    return _row_to_user(row)


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> User | None:
    """Return the user with this id, or None."""
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return _row_to_user(row)


def authenticate(
    conn: sqlite3.Connection, username: str, password: str
) -> User | None:
    """Return the user if the credentials are valid, else None."""
    user = get_user(conn, username)
    if user is None:
        return None
    if not verify_password(user.password_hash, password):
        return None
    return user


def count_users(conn: sqlite3.Connection) -> int:
    """Return the number of stored users (test/diagnostic helper)."""
    return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

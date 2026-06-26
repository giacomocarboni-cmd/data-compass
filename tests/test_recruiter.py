"""
Unit tests for recruiter temporary logins — Phase 6, Step 6.3.

Covers token creation/verification, the lazy access gate (active + not expired +
under cap), usage incrementing, and revocation. No API calls; an in-memory auth
store is used and ``now`` is injected for deterministic expiry tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from data_compass.auth import recruiter, store

_NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    c = store.connect(":memory:")  # shared auth DB; recruiter ensures its table
    yield c
    c.close()


class TestTokenCreationAndVerification:
    def test_token_has_id_dot_secret_format(self, conn):
        token = recruiter.create_recruiter_token(conn, "Acme", now=_NOW)
        assert "." in token
        id_part, secret = token.split(".", 1)
        assert id_part.isdigit() and len(secret) > 10

    def test_valid_token_verifies(self, conn):
        token = recruiter.create_recruiter_token(conn, "Acme", now=_NOW)
        row = recruiter.verify_token(conn, token)
        assert row is not None and row.label == "Acme"

    def test_tampered_secret_fails(self, conn):
        token = recruiter.create_recruiter_token(conn, now=_NOW)
        tid, _ = token.split(".", 1)
        assert recruiter.verify_token(conn, f"{tid}.wrong-secret") is None

    def test_unknown_id_fails(self, conn):
        recruiter.create_recruiter_token(conn, now=_NOW)
        assert recruiter.verify_token(conn, "9999.anything") is None

    def test_malformed_token_fails(self, conn):
        recruiter.ensure_schema(conn)
        for bad in ["", "no-dot", ".secret", "12.", "abc.secret"]:
            assert recruiter.verify_token(conn, bad) is None

    def test_no_plaintext_secret_stored(self, conn):
        token = recruiter.create_recruiter_token(conn, now=_NOW)
        _, secret = token.split(".", 1)
        row = conn.execute("SELECT token_hash FROM recruiter_tokens").fetchone()
        assert secret not in row["token_hash"]


class TestAccessGate:
    def test_valid_within_limits(self, conn):
        token = recruiter.create_recruiter_token(conn, cap=20, days=30, now=_NOW)
        row = recruiter.verify_token(conn, token)
        result = recruiter.check_access(row, now=_NOW)
        assert result.allowed is True
        assert result.reason == "ok"
        assert result.remaining == 20

    def test_blocked_at_query_cap(self, conn):
        token = recruiter.create_recruiter_token(conn, cap=20, days=30, now=_NOW)
        tid = int(token.split(".", 1)[0])
        for _ in range(20):
            recruiter.increment_usage(conn, tid)
        row = recruiter.verify_token(conn, token)
        result = recruiter.check_access(row, now=_NOW)
        assert result.allowed is False
        assert result.reason == "quota_exceeded"

    def test_blocked_after_expiry_regardless_of_remaining_queries(self, conn):
        token = recruiter.create_recruiter_token(conn, cap=20, days=30, now=_NOW)
        row = recruiter.verify_token(conn, token)  # zero queries used
        later = _NOW + timedelta(days=31)
        result = recruiter.check_access(row, now=later)
        assert result.allowed is False
        assert result.reason == "expired"

    def test_allowed_just_before_expiry(self, conn):
        token = recruiter.create_recruiter_token(conn, cap=20, days=30, now=_NOW)
        row = recruiter.verify_token(conn, token)
        nearly = _NOW + timedelta(days=30) - timedelta(seconds=1)
        assert recruiter.check_access(row, now=nearly).allowed is True

    def test_revoked_token_blocked(self, conn):
        token = recruiter.create_recruiter_token(conn, now=_NOW)
        tid = int(token.split(".", 1)[0])
        recruiter.deactivate(conn, tid)
        row = recruiter.verify_token(conn, token)
        result = recruiter.check_access(row, now=_NOW)
        assert result.allowed is False
        assert result.reason == "inactive"


class TestUsageCounter:
    def test_increment_returns_new_count(self, conn):
        token = recruiter.create_recruiter_token(conn, now=_NOW)
        tid = int(token.split(".", 1)[0])
        assert recruiter.increment_usage(conn, tid) == 1
        assert recruiter.increment_usage(conn, tid) == 2

    def test_remaining_decreases_with_use(self, conn):
        token = recruiter.create_recruiter_token(conn, cap=5, now=_NOW)
        tid = int(token.split(".", 1)[0])
        recruiter.increment_usage(conn, tid)
        recruiter.increment_usage(conn, tid)
        row = recruiter.verify_token(conn, token)
        assert recruiter.check_access(row, now=_NOW).remaining == 3

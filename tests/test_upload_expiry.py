"""
Uploaded-dataset cleanup when a recruiter login ends — expiry, quota, logout.

A recruiter's uploaded datasets live only in session state. They must be removed
when the login ends, whether by an explicit logout or by the token reaching its
30-day expiry or 20-query cap. Cleanup is idempotent, so data already removed by
a logout is never removed twice.

No API calls; an isolated in-memory auth store is used.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from data_compass.auth import key_router, recruiter, store
from data_compass.ui import auth as auth_ui
from data_compass.ui.upload import UPLOAD_STATE_KEY, clear_uploaded_datasets


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    recruiter.ensure_schema(c)
    yield c
    c.close()


def _recruiter_session(token_id: int) -> dict:
    """A logged-in recruiter session that has uploaded a dataset."""
    session: dict = {}
    key_router.login_recruiter(session, token_id)
    session[UPLOAD_STATE_KEY] = ["a_parsed_file"]
    session["erd_signed_off"] = True
    return session


def _expire(conn: sqlite3.Connection, token_id: int) -> None:
    conn.execute(
        "UPDATE recruiter_tokens SET expires_at = ? WHERE id = ?",
        ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), token_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# clear_uploaded_datasets — idempotent removal
# ---------------------------------------------------------------------------

class TestClearUploadedDatasets:
    def test_returns_false_when_nothing_loaded(self):
        assert clear_uploaded_datasets({}) is False

    def test_removes_all_upload_state(self):
        session = {
            UPLOAD_STATE_KEY: ["f"],
            "erd_signed_off": True,
            "erd_validation": object(),
            "_uploaded_duckdb_conn": object(),
        }
        assert clear_uploaded_datasets(session) is True
        for key in ("erd_signed_off", "erd_validation", "_uploaded_duckdb_conn"):
            assert key not in session
        assert UPLOAD_STATE_KEY not in session

    def test_idempotent(self):
        session = {UPLOAD_STATE_KEY: ["f"]}
        assert clear_uploaded_datasets(session) is True
        assert clear_uploaded_datasets(session) is False  # nothing left


# ---------------------------------------------------------------------------
# purge_expired_recruiter_uploads — expiry / quota / logout interplay
# ---------------------------------------------------------------------------

class TestPurgeExpiredRecruiterUploads:
    def test_expired_token_clears_uploads_but_keeps_login(self, conn):
        token = recruiter.create_recruiter_token(conn, "Acme")
        tid = int(token.split(".")[0])
        _expire(conn, tid)
        session = _recruiter_session(tid)

        with mock.patch.object(auth_ui.auth_resource, "get_auth_conn",
                               return_value=conn):
            auth_ui.purge_expired_recruiter_uploads(session)

        assert UPLOAD_STATE_KEY not in session
        # Login is left intact so the query gate can show the expiry message.
        assert key_router.is_logged_in(session)

    def test_quota_exhausted_clears_uploads(self, conn):
        token = recruiter.create_recruiter_token(conn, "Acme", cap=1)
        tid = int(token.split(".")[0])
        recruiter.increment_usage(conn, tid)  # 1 of 1 used → over cap
        session = _recruiter_session(tid)

        with mock.patch.object(auth_ui.auth_resource, "get_auth_conn",
                               return_value=conn):
            auth_ui.purge_expired_recruiter_uploads(session)

        assert UPLOAD_STATE_KEY not in session

    def test_valid_token_leaves_uploads_intact(self, conn):
        token = recruiter.create_recruiter_token(conn, "Acme")  # fresh, valid
        tid = int(token.split(".")[0])
        session = _recruiter_session(tid)

        with mock.patch.object(auth_ui.auth_resource, "get_auth_conn",
                               return_value=conn):
            auth_ui.purge_expired_recruiter_uploads(session)

        assert session[UPLOAD_STATE_KEY] == ["a_parsed_file"]
        assert key_router.is_logged_in(session)

    def test_public_session_is_a_noop(self):
        # Already logged out — uploads removed "by the login" must not be touched
        # again, and no auth lookup is needed.
        session = {UPLOAD_STATE_KEY: ["leftover"]}
        auth_ui.purge_expired_recruiter_uploads(session)
        assert session[UPLOAD_STATE_KEY] == ["leftover"]


# ---------------------------------------------------------------------------
# logout also clears uploads (the "already removed by the login" path)
# ---------------------------------------------------------------------------

def test_logout_clears_uploaded_datasets(monkeypatch):
    import streamlit as st

    session = {}
    key_router.login_recruiter(session, 1)
    session[UPLOAD_STATE_KEY] = ["f"]
    monkeypatch.setattr(st, "session_state", session, raising=False)

    auth_ui._cb_logout()

    assert UPLOAD_STATE_KEY not in session
    assert not key_router.is_logged_in(session)

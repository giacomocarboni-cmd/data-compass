"""
Unit tests for the auth store — Phase 6, Step 6.1.

Verifies Argon2id hashing (no plaintext at rest), admin seeding from a secret,
and credential authentication. No API calls; an in-memory SQLite store is used.
"""
from __future__ import annotations

import sqlite3

import pytest

from data_compass.auth import store


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        h = store.hash_password("correct horse battery staple")
        assert "correct horse battery staple" not in h
        assert h.startswith("$argon2")

    def test_verify_correct_password(self):
        h = store.hash_password("s3cret")
        assert store.verify_password(h, "s3cret") is True

    def test_verify_wrong_password(self):
        h = store.hash_password("s3cret")
        assert store.verify_password(h, "wrong") is False

    def test_verify_invalid_hash_returns_false(self):
        assert store.verify_password("not-a-hash", "anything") is False

    def test_hashes_are_salted_and_unique(self):
        assert store.hash_password("same") != store.hash_password("same")


class TestSeedAdmin:
    def test_seeded_admin_verifies_correct_password(self, conn):
        created = store.seed_admin(conn, "admin", "init-pass")
        assert created is True
        user = store.authenticate(conn, "admin", "init-pass")
        assert user is not None
        assert user.role == "admin"

    def test_seeded_admin_rejects_wrong_password(self, conn):
        store.seed_admin(conn, "admin", "init-pass")
        assert store.authenticate(conn, "admin", "WRONG") is None

    def test_no_plaintext_password_stored(self, conn):
        store.seed_admin(conn, "admin", "init-pass")
        row = conn.execute("SELECT password_hash FROM users").fetchone()
        assert "init-pass" not in row["password_hash"]

    def test_seed_is_idempotent(self, conn):
        assert store.seed_admin(conn, "admin", "init-pass") is True
        assert store.seed_admin(conn, "admin", "different") is False
        assert store.count_users(conn) == 1
        # Original password still valid — re-seed did not overwrite it
        assert store.authenticate(conn, "admin", "init-pass") is not None

    def test_blank_seed_password_creates_nothing(self, conn):
        assert store.seed_admin(conn, "admin", "   ") is False
        assert store.count_users(conn) == 0


class TestUserManagement:
    def test_duplicate_username_rejected(self, conn):
        store.create_user(conn, "admin", "p1")
        with pytest.raises(sqlite3.IntegrityError):
            store.create_user(conn, "admin", "p2")

    def test_set_password_changes_credentials(self, conn):
        uid = store.create_user(conn, "admin", "old-pass")
        store.set_password(conn, uid, "new-pass")
        assert store.authenticate(conn, "admin", "old-pass") is None
        assert store.authenticate(conn, "admin", "new-pass") is not None

    def test_get_user_by_id_round_trip(self, conn):
        uid = store.create_user(conn, "admin", "p")
        user = store.get_user_by_id(conn, uid)
        assert user is not None and user.username == "admin"

    def test_unknown_user_authentication_returns_none(self, conn):
        assert store.authenticate(conn, "ghost", "p") is None

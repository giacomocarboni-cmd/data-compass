"""Tests for admin password reset and change."""
from __future__ import annotations

import pytest

from data_compass.auth import policy, store


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    yield c
    c.close()


class TestResetAdminPassword:
    def test_creates_missing_admin(self, conn):
        assert store.reset_admin_password(conn, "admin", "a-long-password") == "created"
        assert store.authenticate(conn, "admin", "a-long-password") is not None

    def test_resets_existing_admin(self, conn):
        store.create_user(conn, "admin", "old-password-123")
        assert store.reset_admin_password(conn, "admin", "new-password-456") == "reset"
        assert store.authenticate(conn, "admin", "old-password-123") is None
        user = store.authenticate(conn, "admin", "new-password-456")
        assert user is not None and not policy.must_change_password(user)

    def test_refuses_short_or_blank(self, conn):
        for bad in ("", "   ", "short"):
            with pytest.raises(ValueError):
                store.reset_admin_password(conn, "admin", bad)
        assert store.count_users(conn) == 0


class TestApplyResetRequest:
    def test_applies_once_per_value(self, conn):
        store.create_user(conn, "admin", "old-password-123")
        assert store.apply_reset_request(conn, "admin", "recovery-pass-1") is True
        store.set_password(conn, store.get_user(conn, "admin").id, "chosen-by-admin-9")
        # Restart with the same secret must not overwrite the admin's own change.
        assert store.apply_reset_request(conn, "admin", "recovery-pass-1") is False
        assert store.authenticate(conn, "admin", "chosen-by-admin-9") is not None

    def test_new_value_applies_again(self, conn):
        assert store.apply_reset_request(conn, "admin", "recovery-pass-1") is True
        assert store.apply_reset_request(conn, "admin", "recovery-pass-2") is True
        assert store.authenticate(conn, "admin", "recovery-pass-2") is not None

    def test_blank_is_ignored(self, conn):
        assert store.apply_reset_request(conn, "admin", "") is False
        assert store.count_users(conn) == 0

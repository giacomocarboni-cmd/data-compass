"""
Unit tests for the admin password renewal policy — Phase 6, Step 6.2.

Pure date logic; no I/O, no API calls. A User is constructed directly with a
controlled ``password_set_at`` and ``now`` is injected for determinism.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from data_compass.auth import policy
from data_compass.auth.store import User

_NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


def _admin(set_at: datetime, role: str = "admin") -> User:
    return User(
        id=1,
        username="admin",
        password_hash="$argon2id$dummy",
        role=role,
        password_set_at=set_at.isoformat(),
        created_at=set_at.isoformat(),
    )


class TestMustChangePassword:
    def test_fresh_password_within_30_days(self):
        user = _admin(_NOW - timedelta(days=5))
        assert policy.must_change_password(user, now=_NOW) is False

    def test_password_older_than_30_days(self):
        user = _admin(_NOW - timedelta(days=31))
        assert policy.must_change_password(user, now=_NOW) is True

    def test_exactly_30_days_not_yet_expired(self):
        user = _admin(_NOW - timedelta(days=30))
        assert policy.must_change_password(user, now=_NOW) is False

    def test_just_over_30_days_expired(self):
        user = _admin(_NOW - timedelta(days=30, seconds=1))
        assert policy.must_change_password(user, now=_NOW) is True

    def test_non_admin_never_forced(self):
        user = _admin(_NOW - timedelta(days=999), role="recruiter")
        assert policy.must_change_password(user, now=_NOW) is False

    def test_custom_max_age(self):
        user = _admin(_NOW - timedelta(days=8))
        assert policy.must_change_password(user, now=_NOW, max_age_days=7) is True
        assert policy.must_change_password(user, now=_NOW, max_age_days=14) is False


class TestAgeHelpers:
    def test_password_age_days(self):
        user = _admin(_NOW - timedelta(days=10))
        assert round(policy.password_age_days(user, now=_NOW)) == 10

    def test_days_until_renewal_positive_when_fresh(self):
        user = _admin(_NOW - timedelta(days=10))
        assert round(policy.days_until_renewal(user, now=_NOW)) == 20

    def test_days_until_renewal_negative_when_overdue(self):
        user = _admin(_NOW - timedelta(days=40))
        assert policy.days_until_renewal(user, now=_NOW) < 0

    def test_naive_timestamp_treated_as_utc(self):
        # password_set_at without tz offset must not raise and must compute sanely
        naive = (_NOW - timedelta(days=5)).replace(tzinfo=None)
        user = _admin_naive = User(
            id=1, username="admin", password_hash="x", role="admin",
            password_set_at=naive.isoformat(), created_at=naive.isoformat(),
        )
        assert policy.must_change_password(user, now=_NOW) is False
        assert round(policy.password_age_days(user, now=_NOW)) == 5

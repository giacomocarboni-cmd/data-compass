"""
Admin password renewal policy — Phase 6, Step 6.2.

Admin passwords expire after a fixed age (default 30 days, configurable via
``ADMIN_PASSWORD_MAX_AGE_DAYS``). The login flow checks ``must_change_password``
and forces a renewal before granting admin access. This is pure date logic with
no I/O, so it is trivially testable.
"""
from __future__ import annotations

from datetime import datetime, timezone

from data_compass.auth.store import User
from data_compass.config import ADMIN_PASSWORD_MAX_AGE_DAYS


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp, assuming UTC if no tzinfo is present."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def password_age_days(
    user: User,
    *,
    now: datetime | None = None,
) -> float:
    """Return the age of the user's current password, in days."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    set_at = _parse_ts(user.password_set_at)
    return (now - set_at).total_seconds() / 86400.0


def must_change_password(
    user: User,
    *,
    now: datetime | None = None,
    max_age_days: int = ADMIN_PASSWORD_MAX_AGE_DAYS,
) -> bool:
    """Return True if the user's password is older than the maximum age.

    Only admins are subject to renewal; non-admin roles are never forced.
    """
    if user.role != "admin":
        return False
    return password_age_days(user, now=now) > max_age_days


def days_until_renewal(
    user: User,
    *,
    now: datetime | None = None,
    max_age_days: int = ADMIN_PASSWORD_MAX_AGE_DAYS,
) -> float:
    """Return days remaining before renewal is required (negative if overdue)."""
    return max_age_days - password_age_days(user, now=now)

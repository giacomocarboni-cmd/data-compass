"""
Phase 8, Step 8.4 — Town/Postcode consent records + withdrawal tests.

Covers:
  * opt-in is recorded and has_consent reflects it;
  * withdrawal flips has_consent to False and the record shows withdrawn_at +
    active False (so retention is removed and the trail is preserved);
  * re-granting after withdrawal works and supersedes the old record;
  * consent is isolated per subject and per scope;
  * unknown subjects/scopes have no consent.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from data_compass.auth import store
from data_compass.gdpr import consent


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    consent.ensure_schema(c)
    yield c
    c.close()


_SUBJECT = "upload:recruiter:7"
_OTHER = "upload:admin:owner"


class TestGrant:
    def test_opt_in_recorded(self, conn):
        consent.grant_consent(conn, _SUBJECT)
        assert consent.has_consent(conn, _SUBJECT) is True

    def test_record_fields_populated(self, conn):
        consent.grant_consent(conn, _SUBJECT)
        rec = consent.get_consent(conn, _SUBJECT)
        assert rec is not None
        assert rec.subject == _SUBJECT
        assert rec.scope == consent.DEFAULT_SCOPE
        assert rec.active is True
        assert rec.withdrawn_at is None

    def test_no_consent_for_unknown_subject(self, conn):
        assert consent.has_consent(conn, "upload:recruiter:999") is False
        assert consent.get_consent(conn, "upload:recruiter:999") is None


class TestWithdraw:
    def test_withdrawal_removes_consent(self, conn):
        consent.grant_consent(conn, _SUBJECT)
        withdrawn = consent.withdraw_consent(conn, _SUBJECT)
        assert withdrawn is True
        assert consent.has_consent(conn, _SUBJECT) is False

    def test_record_reflects_withdrawal(self, conn):
        consent.grant_consent(conn, _SUBJECT)
        consent.withdraw_consent(conn, _SUBJECT)
        rec = consent.get_consent(conn, _SUBJECT)
        assert rec.active is False
        assert rec.withdrawn_at is not None

    def test_withdraw_without_consent_returns_false(self, conn):
        assert consent.withdraw_consent(conn, _SUBJECT) is False

    def test_regrant_after_withdrawal(self, conn):
        consent.grant_consent(conn, _SUBJECT)
        consent.withdraw_consent(conn, _SUBJECT)
        consent.grant_consent(conn, _SUBJECT)
        assert consent.has_consent(conn, _SUBJECT) is True
        rec = consent.get_consent(conn, _SUBJECT)
        assert rec.active is True
        assert rec.withdrawn_at is None


class TestIsolation:
    def test_subject_isolation(self, conn):
        consent.grant_consent(conn, _SUBJECT)
        assert consent.has_consent(conn, _OTHER) is False

    def test_scope_isolation(self, conn):
        consent.grant_consent(conn, _SUBJECT, scope="town_postcode")
        assert consent.has_consent(conn, _SUBJECT, scope="full_address") is False

    def test_grant_supersedes_prior_active(self, conn):
        # Two grants → only one active row in force.
        consent.grant_consent(conn, _SUBJECT, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        consent.grant_consent(conn, _SUBJECT, now=datetime(2026, 2, 1, tzinfo=timezone.utc))
        active = conn.execute(
            "SELECT COUNT(*) FROM consent_records WHERE subject=? AND active=1",
            (_SUBJECT,),
        ).fetchone()[0]
        assert active == 1

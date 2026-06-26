"""
Phase 8, Step 8.6 — PII audit log tests.

Covers:
  * a detection event is logged with its resolution and round-trips;
  * detections store column/type/count only (value-free);
  * multiple events are returned most-recent-first and can be filtered by
    subject.
"""
from __future__ import annotations

import pandas as pd
import pytest

from data_compass.auth import store
from data_compass.gdpr import audit
from data_compass.pii.scan import scan_dataframe


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    audit.ensure_schema(c)
    yield c
    c.close()


_SUBJECT = "upload:recruiter:7"


def _findings():
    df = pd.DataFrame({
        "email": ["a@b.com", "c@d.com"],
        "postcode": ["SW1A 1AA", "M1 1AE"],
    })
    return scan_dataframe("members", df).findings


class TestLogDetection:
    def test_event_logged_with_resolution(self, conn):
        entry = audit.log_detection(
            conn, _SUBJECT, "members", _findings(), audit.RESOLUTION_MASKED
        )
        assert entry.id > 0
        assert entry.resolution == audit.RESOLUTION_MASKED
        assert entry.subject == _SUBJECT
        assert entry.table_name == "members"

    def test_detections_recorded_value_free(self, conn):
        audit.log_detection(
            conn, _SUBJECT, "members", _findings(), audit.RESOLUTION_MASKED
        )
        entries = audit.get_entries(conn, _SUBJECT)
        assert len(entries) == 1
        detected = {d.pii_type for d in entries[0].detections}
        assert detected == {"email", "uk_postcode"}
        # Column names + counts only — no raw values anywhere.
        for d in entries[0].detections:
            assert isinstance(d.count, int)
            assert d.column in {"email", "postcode"}

    def test_resolution_round_trips(self, conn):
        audit.log_detection(
            conn, _SUBJECT, "t", _findings(), audit.RESOLUTION_CANCELLED,
            detail="user cancelled",
        )
        entry = audit.get_entries(conn, _SUBJECT)[0]
        assert entry.resolution == audit.RESOLUTION_CANCELLED
        assert entry.detail == "user cancelled"


class TestQuery:
    def test_multiple_entries_most_recent_first(self, conn):
        audit.log_detection(conn, _SUBJECT, "t1", _findings(), audit.RESOLUTION_MASKED)
        audit.log_detection(conn, _SUBJECT, "t2", _findings(), audit.RESOLUTION_RETAINED)
        entries = audit.get_entries(conn, _SUBJECT)
        assert [e.table_name for e in entries] == ["t2", "t1"]

    def test_subject_filter(self, conn):
        audit.log_detection(conn, _SUBJECT, "t", _findings(), audit.RESOLUTION_MASKED)
        audit.log_detection(conn, "upload:admin:owner", "t", _findings(), audit.RESOLUTION_MASKED)
        assert len(audit.get_entries(conn, _SUBJECT)) == 1
        assert len(audit.get_entries(conn)) == 2

"""
PII detection/resolution audit log — Phase 8, Step 8.6.

An append-only accountability trail: every time the failsafe detects personal
data in an upload, one entry records what was found and how it was resolved
(masked, retained under consent, or the upload was cancelled). This supports
the "demonstrate accountability" limb of GDPR and gives the owner evidence of
the control operating.

Records live in the shared SQLite auth DB. The detections are stored as a
compact JSON array of ``{column, pii_type, count}`` — column names and counts
only, never the underlying values (those are masked before anything is stored).

Schema (table ``pii_audit_log``):
  id          INTEGER PK
  logged_at   TEXT  — ISO-8601 UTC
  subject     TEXT  — per-user identity (key_router.get_upload_scope)
  table_name  TEXT  — the uploaded table the detection relates to
  detections  TEXT  — JSON array of {column, pii_type, count}
  resolution  TEXT  — 'masked' | 'retained_with_consent' | 'cancelled' | ...
  detail      TEXT  — optional free-text note

Public API
----------
RESOLUTION_MASKED / RETAINED / CANCELLED   resolution constants
Detection / AuditEntry                     dataclasses
ensure_schema(conn)
log_detection(conn, subject, table_name, findings, resolution, *, detail, now) -> AuditEntry
get_entries(conn, subject=None) -> list[AuditEntry]
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from data_compass.pii.scan import PiiFinding

RESOLUTION_MASKED = "masked"
RESOLUTION_RETAINED = "retained_with_consent"
RESOLUTION_CANCELLED = "cancelled"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pii_audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at   TEXT NOT NULL,
    subject     TEXT NOT NULL,
    table_name  TEXT NOT NULL,
    detections  TEXT NOT NULL,
    resolution  TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT ''
);
"""


@dataclass
class Detection:
    """A single column-level detection, value-free."""
    column: str
    pii_type: str
    count: int


@dataclass
class AuditEntry:
    """One logged detection/resolution event."""
    id: int
    logged_at: str
    subject: str
    table_name: str
    detections: list[Detection] = field(default_factory=list)
    resolution: str = ""
    detail: str = ""


def _now(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now


def _detections_from_findings(findings: Iterable[PiiFinding]) -> list[Detection]:
    return [Detection(f.column, f.pii_type, f.match_count) for f in findings]


def _serialise(detections: list[Detection]) -> str:
    return json.dumps(
        [{"column": d.column, "pii_type": d.pii_type, "count": d.count} for d in detections]
    )


def _deserialise(text: str) -> list[Detection]:
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        return []
    return [
        Detection(i.get("column", ""), i.get("pii_type", ""), int(i.get("count", 0)))
        for i in items
        if isinstance(i, dict)
    ]


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the pii_audit_log table if absent (shares the auth DB)."""
    conn.executescript(_SCHEMA)
    conn.commit()


def _row_to_entry(row: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        id=row["id"],
        logged_at=row["logged_at"],
        subject=row["subject"],
        table_name=row["table_name"],
        detections=_deserialise(row["detections"]),
        resolution=row["resolution"],
        detail=row["detail"],
    )


def log_detection(
    conn: sqlite3.Connection,
    subject: str,
    table_name: str,
    findings: Iterable[PiiFinding],
    resolution: str,
    *,
    detail: str = "",
    now: datetime | None = None,
) -> AuditEntry:
    """Append one detection/resolution event and return it."""
    ensure_schema(conn)
    detections = _detections_from_findings(findings)
    cur = conn.execute(
        """
        INSERT INTO pii_audit_log
            (logged_at, subject, table_name, detections, resolution, detail)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            _now(now).isoformat(),
            subject,
            table_name,
            _serialise(detections),
            resolution,
            detail,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM pii_audit_log WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _row_to_entry(row)


def get_entries(
    conn: sqlite3.Connection,
    subject: str | None = None,
) -> list[AuditEntry]:
    """Return logged events (most recent first), optionally filtered by subject."""
    ensure_schema(conn)
    if subject is None:
        rows = conn.execute(
            "SELECT * FROM pii_audit_log ORDER BY id DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM pii_audit_log WHERE subject = ? ORDER BY id DESC",
            (subject,),
        ).fetchall()
    return [_row_to_entry(r) for r in rows]

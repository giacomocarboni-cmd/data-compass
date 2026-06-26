"""
Phase 8, Step 8.2 — Block-and-warn + mask-before-API (UI journey, AppTest).

A logged-in user has files in session that contain personal data (an email
column and a postcode column). On the Upload tab the PII gate must:

  1. block the journey — report the findings, and NOT render the downstream
     relationships form (so nothing reaches a prompt or the cache);
  2. on "Mask and continue", mask the flagged columns in place, replace the
     stored files with masked copies, and let the journey proceed;
  3. leave no raw PII in the stored (now masked) data.

No Anthropic API call is involved in this flow (masking is deterministic).
"""
from __future__ import annotations

from unittest import mock

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from data_compass.auth import recruiter, store
from data_compass.i18n import t
from data_compass.upload.ingest import ParsedFile

_OWNER_KEY = "sk-ant-owner-pii-test"

_PII_FILE = ParsedFile(
    "members.csv",
    pd.DataFrame({
        "member_id": [1, 2, 3],
        "email": ["alice@example.com", "bob@test.co.uk", "carol@d.org"],
        "postcode": ["SW1A 1AA", "M1 1AE", "B33 8TH"],
    }),
)


@pytest.fixture
def auth_conn():
    c = store.connect(":memory:")
    recruiter.ensure_schema(c)
    yield c
    c.close()


def _patches(auth_conn):
    return (
        mock.patch("data_compass.auth.resource.get_auth_conn", return_value=auth_conn),
        mock.patch("data_compass.config.OWNER_API_KEY", _OWNER_KEY),
    )


def _input_by_label(at, label: str):
    return next(ti for ti in at.text_input if ti.label == label)


def _button_by_label(at, label: str):
    return next(b for b in at.button if b.label == label)


def _nav(at, dest: str):
    return at.radio[0].set_value(dest).run()


def _login_recruiter(at, token: str):
    at = _nav(at, t("app.nav.account"))
    _input_by_label(at, t("auth.recruiter_token_label")).set_value(token)
    return _button_by_label(at, t("auth.recruiter_login_button")).click().run()


class TestPiiGate:
    def test_block_then_mask_flow(self, auth_conn):
        token = recruiter.create_recruiter_token(auth_conn, "TestCorp", cap=10)
        p1, p2 = _patches(auth_conn)
        with p1, p2:
            at = AppTest.from_file("app.py", default_timeout=60)
            at.session_state["uploaded_files"] = [_PII_FILE]
            at.session_state["tos_accepted"] = True  # ToS gate tested separately
            at = at.run()

            at = _login_recruiter(at, token)
            assert at.session_state["auth_tier"] == "recruiter"

            # Navigate to Upload — the gate should block and report.
            at = _nav(at, t("app.nav.upload"))

            errors = " ".join(e.value for e in at.error)
            assert t("pii.blocked_header") in errors

            # Downstream relationships form must NOT be present while blocked.
            confirm = next(
                (b for b in at.button if b.label == t("relationships.confirm_button")),
                None,
            )
            assert confirm is None, "Relationships form rendered while PII unresolved"

            # Click "Mask and continue".
            at = _button_by_label(at, t("pii.mask_button")).click().run()

        # Resolved: stored files are masked, raw values gone.
        assert at.session_state["pii_resolved"] is True
        masked_files = at.session_state["uploaded_files"]
        masked_df = masked_files[0].df
        assert all(v.startswith("EMAIL_") for v in masked_df["email"])
        assert all(v.startswith("POSTCODE_") for v in masked_df["postcode"])
        blob = masked_df.to_csv(index=False)
        assert "alice@example.com" not in blob
        assert "SW1A 1AA" not in blob
        # Non-PII column preserved.
        assert list(masked_df["member_id"]) == [1, 2, 3]

        # After masking, the downstream relationships form is now available.
        confirm_after = next(
            (b for b in at.button if b.label == t("relationships.confirm_button")),
            None,
        )
        assert confirm_after is not None, "Relationships form missing after masking"

    def test_clean_file_not_blocked(self, auth_conn):
        token = recruiter.create_recruiter_token(auth_conn, "TestCorp", cap=10)
        clean = ParsedFile(
            "products.csv",
            pd.DataFrame({"sku": ["A1", "B2"], "price": [9.99, 14.5]}),
        )
        p1, p2 = _patches(auth_conn)
        with p1, p2:
            at = AppTest.from_file("app.py", default_timeout=60)
            at.session_state["uploaded_files"] = [clean]
            at.session_state["tos_accepted"] = True
            at = at.run()
            at = _login_recruiter(at, token)
            at = _nav(at, t("app.nav.upload"))

        errors = " ".join(e.value for e in at.error)
        assert t("pii.blocked_header") not in errors
        assert at.session_state["pii_resolved"] is True
        # Relationships form is reachable for a clean upload.
        confirm = next(
            (b for b in at.button if b.label == t("relationships.confirm_button")),
            None,
        )
        assert confirm is not None

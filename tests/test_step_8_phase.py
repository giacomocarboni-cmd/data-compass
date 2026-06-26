"""
Phase 8 — completion test (user journey, AppTest).

A logged-in user attempts to upload a file containing emails and postcodes.
The app:
  1. requires the Terms of Use to be accepted before any uploader appears;
  2. blocks the upload and reports the personal data found;
  3. presents a Town/Postcode consent prompt;
  4. on "Mask and continue" (with consent to retain Town/Postcode), masks the
     email before anything proceeds while retaining the postcode under consent;
  5. records the consent and logs the detection events.

No AI/Anthropic call occurs anywhere in this journey (masking and consent are
deterministic); the masking happens before any prompt could be issued.
"""
from __future__ import annotations

from unittest import mock

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from data_compass.auth import recruiter, store
from data_compass.gdpr import audit, consent
from data_compass.i18n import t
from data_compass.upload.ingest import ParsedFile

_OWNER_KEY = "sk-ant-owner-phase8-test"

_PII_FILE = ParsedFile(
    "members.csv",
    pd.DataFrame({
        "member_id": [1, 2, 3],
        "email": ["alice@example.com", "bob@test.co.uk", "carol@d.org"],
        "postcode": ["SW1A 1AA", "M1 1AE", "B33 8TH"],
        "town": ["London", "Manchester", "Birmingham"],
    }),
)


@pytest.fixture
def auth_conn():
    c = store.connect(":memory:")
    recruiter.ensure_schema(c)
    yield c
    c.close()


def _patches(auth_conn):
    # If any Anthropic call were attempted, this mock would raise.
    failing_client = mock.MagicMock()
    failing_client.messages.create.side_effect = AssertionError("No AI call expected")
    return (
        mock.patch("data_compass.auth.resource.get_auth_conn", return_value=auth_conn),
        mock.patch("data_compass.config.OWNER_API_KEY", _OWNER_KEY),
        mock.patch("anthropic.Anthropic", return_value=failing_client),
    )


def _input_by_label(at, label):
    return next(ti for ti in at.text_input if ti.label == label)


def _button_by_label(at, label):
    return next(b for b in at.button if b.label == label)


def _nav(at, dest):
    return at.radio[0].set_value(dest).run()


def test_phase8_upload_pii_block_consent_mask_log(auth_conn):
    token = recruiter.create_recruiter_token(auth_conn, "TestCorp", cap=10)
    p1, p2, p3 = _patches(auth_conn)
    with p1, p2, p3:
        at = AppTest.from_file("app.py", default_timeout=60)
        at.session_state["uploaded_files"] = [_PII_FILE]
        at = at.run()

        # Log in.
        at = _nav(at, t("app.nav.account"))
        _input_by_label(at, t("auth.recruiter_token_label")).set_value(token)
        at = _button_by_label(at, t("auth.recruiter_login_button")).click().run()
        assert at.session_state["auth_tier"] == "recruiter"

        # Upload tab: ToS required first (no uploader yet).
        at = _nav(at, t("app.nav.upload"))
        assert len(at.file_uploader) == 0
        tos_cb = next(cb for cb in at.checkbox if cb.label == t("legal.tos_accept_checkbox"))
        at = tos_cb.check().run()
        at = _button_by_label(at, t("legal.tos_accept_button")).click().run()

        # PII block is reported, with the Town/Postcode consent prompt.
        errors = " ".join(e.value for e in at.error)
        assert t("pii.blocked_header") in errors
        retain_cb = next(cb for cb in at.checkbox if cb.label == t("pii.retain_postcode"))
        at = retain_cb.check().run()

        # Mask-and-continue (retaining Town/Postcode under consent).
        at = _button_by_label(at, t("pii.mask_button")).click().run()

    # The consent/audit subject for a recruiter is keyed by the token id.
    token_id = int(token.split(".")[0])
    subject = f"upload:recruiter:{token_id}"

    # Email masked; postcode retained under consent; non-PII untouched.
    masked_df = at.session_state["uploaded_files"][0].df
    assert all(v.startswith("EMAIL_") for v in masked_df["email"])
    assert list(masked_df["postcode"]) == ["SW1A 1AA", "M1 1AE", "B33 8TH"]
    assert list(masked_df["member_id"]) == [1, 2, 3]

    # Consent recorded.
    assert consent.has_consent(auth_conn, subject) is True

    # Detection events logged: a masked (email) and a retained (postcode) entry.
    entries = audit.get_entries(auth_conn, subject)
    resolutions = {e.resolution for e in entries}
    assert audit.RESOLUTION_MASKED in resolutions
    assert audit.RESOLUTION_RETAINED in resolutions
    masked_types = {
        d.pii_type
        for e in entries if e.resolution == audit.RESOLUTION_MASKED
        for d in e.detections
    }
    assert "email" in masked_types

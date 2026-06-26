"""
Phase 8, Step 8.5 — ToS upload gate + privacy notice + caching warning (AppTest).

Covers the user journey:
  * a logged-in user visiting Upload is blocked until they accept the Terms of
    Use — no file uploader appears beforehand;
  * the Privacy Notice is reachable from the UI (controller named) and the ToS
    text carries a clearly-marked DRAFT note;
  * after accepting, the uploader appears;
  * the caching warning is shown on the Query panel (to all tiers).
"""
from __future__ import annotations

from unittest import mock

import pytest
from streamlit.testing.v1 import AppTest

from data_compass.auth import recruiter, store
from data_compass.i18n import t

_OWNER_KEY = "sk-ant-owner-legal-test"


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


class TestTosGate:
    def test_upload_blocked_until_tos_accepted(self, auth_conn):
        token = recruiter.create_recruiter_token(auth_conn, "TestCorp", cap=10)
        p1, p2 = _patches(auth_conn)
        with p1, p2:
            at = AppTest.from_file("app.py", default_timeout=60).run()
            at = _login_recruiter(at, token)
            at = _nav(at, t("app.nav.upload"))

            # Blocked: ToS shown, DRAFT note present, no uploader yet.
            subheaders = " ".join(s.value for s in at.subheader)
            assert t("legal.tos_header") in subheaders
            captions = " ".join(c.value for c in at.caption)
            assert "DRAFT" in captions
            assert len(at.file_uploader) == 0

            # Privacy Notice is reachable (controller named).
            body = " ".join(m.value for m in at.markdown)
            assert "giacomo.carboni@gmail.com" in body

            # Accept the ToS.
            tos_cb = next(
                cb for cb in at.checkbox if cb.label == t("legal.tos_accept_checkbox")
            )
            at = tos_cb.check().run()
            at = _button_by_label(at, t("legal.tos_accept_button")).click().run()

        assert at.session_state["tos_accepted"] is True
        # Uploader now present.
        assert len(at.file_uploader) == 1

    def test_caching_warning_on_query_panel(self, auth_conn):
        # Public (BYOK) tier still sees the caching warning on the Query panel.
        p1, p2 = _patches(auth_conn)
        with p1, p2:
            at = AppTest.from_file("app.py", default_timeout=60).run()
            at = _nav(at, t("app.nav.query"))

        captions = " ".join(c.value for c in at.caption)
        assert t("legal.caching_warning") in captions

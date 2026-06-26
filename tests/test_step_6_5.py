"""
Phase 6 completion test — authentication & tiers wired into the running app.

User journey (AppTest, all API calls mocked):
  * A recruiter logs in with an access token on the Account page, then runs
    queries on the Query page using the *owner* key (no BYOK needed). The quota
    counter increments per query, and once the cap is reached further queries are
    blocked with a clear message.
  * A public visitor (no login) still queries using their own BYOK key.

The Anthropic SDK is mocked at the lowest level; the local embedder is replaced
with a fake vector; DuckDB execution is real; auth + cache use isolated in-memory
SQLite stores.
"""
from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from data_compass.auth import recruiter, store
from data_compass.cache import store as cache_store
from data_compass.config import MODEL_SONNET
from data_compass.i18n import t

_OWNER_KEY = "sk-ant-owner-test"

_TEMPLATE_SQL = (
    "SELECT p.county, COUNT(*) AS sales "
    "FROM transactions t JOIN properties p ON t.property_id = p.property_id "
    "GROUP BY p.county ORDER BY sales DESC LIMIT 5"
)
_GEN_PAYLOAD = (
    '{"sql_template": "' + _TEMPLATE_SQL + '", "param_defs": [], "params": {}}'
)
_QUESTION = "How many sales per county?"


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _usage(inp=400, out=80):
    u = MagicMock()
    u.input_tokens = inp
    u.output_tokens = out
    u.cache_creation_input_tokens = 0
    u.cache_read_input_tokens = 0
    return u


def _sdk_response(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = _usage()
    return resp


def _make_client():
    def _create(*args, model=None, **kwargs):
        if model == MODEL_SONNET:
            return _sdk_response(_GEN_PAYLOAD)
        return _sdk_response("Greater London leads on sales.")

    client = MagicMock()
    client.messages.create.side_effect = _create
    return client


def _fake_embed(texts):
    return np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)


# ---------------------------------------------------------------------------
# AppTest widget helpers (find by label/text, robust to layout changes)
# ---------------------------------------------------------------------------

def _input_by_label(at, label: str):
    return next(ti for ti in at.text_input if ti.label == label)


def _button_by_label(at, label: str):
    return next(b for b in at.button if b.label == label)


def _select_dataset(at):
    picker = next(
        sb for sb in at.selectbox
        if "dataset" in sb.label.lower() or "Demo" in sb.label
    )
    return picker.select("UK Property Sales 2024").run()


def _nav(at, dest: str):
    return at.radio[0].set_value(dest).run()


def _ask(at, question: str):
    at.text_area[0].set_value(question)
    return _button_by_label(at, t("query.submit_button")).click().run()


def _tier(at) -> str:
    return at.session_state["auth_tier"] if "auth_tier" in at.session_state else "public"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cache_conn():
    c = cache_store.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def auth_conn():
    c = store.connect(":memory:")
    recruiter.ensure_schema(c)
    yield c
    c.close()


def _patches(auth_conn, cache_conn):
    """Standard patch set: isolated stores, fake embedder, mocked SDK, owner key."""
    return (
        mock.patch("data_compass.auth.resource.get_auth_conn", return_value=auth_conn),
        mock.patch("data_compass.cache.resource.get_cache_conn", return_value=cache_conn),
        mock.patch(
            "data_compass.cache.generate.embed_question",
            side_effect=lambda q, embed_fn=None: _fake_embed([q])[0],
        ),
        mock.patch("anthropic.Anthropic", return_value=_make_client()),
        mock.patch("data_compass.config.OWNER_API_KEY", _OWNER_KEY),
    )


# ---------------------------------------------------------------------------
# Recruiter journey
# ---------------------------------------------------------------------------

class TestRecruiterJourney:
    def _login_recruiter(self, at, token: str):
        at = _nav(at, t("app.nav.account"))
        _input_by_label(at, t("auth.recruiter_token_label")).set_value(token)
        return _button_by_label(at, t("auth.recruiter_login_button")).click().run()

    def test_recruiter_login_then_query_uses_owner_key_and_counts(
        self, auth_conn, cache_conn
    ):
        token = recruiter.create_recruiter_token(auth_conn, "Acme", cap=5)
        token_id = int(token.split(".", 1)[0])

        p1, p2, p3, p4, p5 = _patches(auth_conn, cache_conn)
        with p1, p2, p3, p4, p5:
            at = AppTest.from_file("app.py", default_timeout=60).run()
            at = _select_dataset(at)
            at = self._login_recruiter(at, token)

            # Logged in as recruiter (no BYOK key was ever entered)
            assert _tier(at) == "recruiter"

            at = _nav(at, t("app.nav.query"))
            at = _ask(at, _QUESTION)
            result = at.session_state["query_result"]

        # The query ran (owner key) and was not blocked; counter incremented to 1.
        assert result.cache_tier == "miss"
        assert result.error is None
        assert recruiter.get_token(auth_conn, token_id).queries_used == 1

    def test_recruiter_blocked_at_cap(self, auth_conn, cache_conn):
        token = recruiter.create_recruiter_token(auth_conn, "Acme", cap=2)
        token_id = int(token.split(".", 1)[0])

        p1, p2, p3, p4, p5 = _patches(auth_conn, cache_conn)
        with p1, p2, p3, p4, p5:
            at = AppTest.from_file("app.py", default_timeout=60).run()
            at = _select_dataset(at)
            at = self._login_recruiter(at, token)
            at = _nav(at, t("app.nav.query"))

            at = _ask(at, _QUESTION)   # 1st — allowed (miss)
            at = _ask(at, _QUESTION)   # 2nd — allowed (exact hit)
            used_at_cap = recruiter.get_token(auth_conn, token_id).queries_used
            at = _ask(at, _QUESTION)   # 3rd — blocked
            blocked = at.session_state["query_result"]
            errors = " ".join(e.value for e in at.error)

        assert used_at_cap == 2
        assert blocked.cache_tier == "blocked"
        assert blocked.error == "blocked:quota_exceeded"
        # Counter did not advance past the cap
        assert recruiter.get_token(auth_conn, token_id).queries_used == 2
        # A clear, localised message is shown
        assert t("query.blocked_quota") in errors

    def test_invalid_token_does_not_log_in(self, auth_conn, cache_conn):
        p1, p2, p3, p4, p5 = _patches(auth_conn, cache_conn)
        with p1, p2, p3, p4, p5:
            at = AppTest.from_file("app.py", default_timeout=60).run()
            at = _select_dataset(at)
            at = _nav(at, t("app.nav.account"))
            _input_by_label(at, t("auth.recruiter_token_label")).set_value(
                "999.not-a-real-secret"
            )
            at = _button_by_label(at, t("auth.recruiter_login_button")).click().run()
            errors = " ".join(e.value for e in at.error)

        assert _tier(at) == "public"
        assert t("auth.token_invalid") in errors


# ---------------------------------------------------------------------------
# Admin journey
# ---------------------------------------------------------------------------

class TestAdminJourney:
    def test_admin_login_with_seeded_credentials(self, auth_conn, cache_conn):
        store.seed_admin(auth_conn, "admin", "init-pass")

        p1, p2, p3, p4, p5 = _patches(auth_conn, cache_conn)
        with p1, p2, p3, p4, p5:
            at = AppTest.from_file("app.py", default_timeout=60).run()
            at = _nav(at, t("app.nav.account"))
            _input_by_label(at, t("auth.admin_username_label")).set_value("admin")
            _input_by_label(at, t("auth.admin_password_label")).set_value("init-pass")
            at = _button_by_label(at, t("auth.admin_login_button")).click().run()

        assert _tier(at) == "admin"


# ---------------------------------------------------------------------------
# Public tier still works with BYOK
# ---------------------------------------------------------------------------

class TestPublicTier:
    def test_public_uses_byok_without_login(self, auth_conn, cache_conn):
        p1, p2, p3, p4, p5 = _patches(auth_conn, cache_conn)
        with p1, p2, p3, p4, p5:
            at = AppTest.from_file("app.py", default_timeout=60).run()
            at = _select_dataset(at)
            # Public visitor enters their own key in the sidebar
            _input_by_label(at, t("sidebar.api_key_label")).set_value("sk-ant-byok")
            at = _nav(at, t("app.nav.query"))
            at = _ask(at, _QUESTION)
            result = at.session_state["query_result"]

        assert _tier(at) == "public"
        assert result.error is None
        assert result.cache_tier == "miss"
        # No recruiter quota was consumed by a public query
        assert cache_store.count_templates(cache_conn) == 1

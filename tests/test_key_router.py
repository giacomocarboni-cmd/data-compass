"""
Unit tests for API-key routing by tier — Phase 6, Step 6.4.

A plain dict stands in for Streamlit session state. The owner key is injected so
the tests never depend on the environment. No API calls.
"""
from __future__ import annotations

from data_compass.auth import api_key, key_router

_OWNER = "sk-ant-owner-key"
_BYOK = "sk-ant-visitor-key"


class TestTierState:
    def test_default_tier_is_public(self):
        assert key_router.get_tier({}) == key_router.TIER_PUBLIC

    def test_login_admin_sets_tier(self):
        s: dict = {}
        key_router.login_admin(s, "admin")
        assert key_router.get_tier(s) == key_router.TIER_ADMIN
        assert key_router.is_logged_in(s) is True

    def test_login_recruiter_records_token_id(self):
        s: dict = {}
        key_router.login_recruiter(s, 42)
        assert key_router.get_tier(s) == key_router.TIER_RECRUITER
        assert key_router.get_recruiter_token_id(s) == 42

    def test_logout_returns_to_public(self):
        s: dict = {}
        key_router.login_admin(s, "admin")
        key_router.logout(s)
        assert key_router.get_tier(s) == key_router.TIER_PUBLIC
        assert key_router.is_logged_in(s) is False

    def test_switching_tiers_clears_other_identity(self):
        s: dict = {}
        key_router.login_recruiter(s, 7)
        key_router.login_admin(s, "admin")
        assert key_router.get_recruiter_token_id(s) is None


class TestKeyResolution:
    def test_public_uses_byok(self):
        s: dict = {}
        api_key.set_key(s, _BYOK)
        res = key_router.resolve_api_key(s, owner_key=_OWNER)
        assert res.key == _BYOK
        assert res.source == "byok"
        assert res.tier == key_router.TIER_PUBLIC

    def test_public_without_byok_returns_none(self):
        res = key_router.resolve_api_key({}, owner_key=_OWNER)
        assert res.key is None
        assert res.source == "none"

    def test_admin_uses_owner_key(self):
        s: dict = {}
        key_router.login_admin(s, "admin")
        api_key.set_key(s, _BYOK)  # even if a BYOK key lingers, owner wins
        res = key_router.resolve_api_key(s, owner_key=_OWNER)
        assert res.key == _OWNER
        assert res.source == "owner"

    def test_recruiter_uses_owner_key(self):
        s: dict = {}
        key_router.login_recruiter(s, 1)
        res = key_router.resolve_api_key(s, owner_key=_OWNER)
        assert res.key == _OWNER
        assert res.source == "owner"

    def test_logged_in_without_owner_key_returns_none(self):
        s: dict = {}
        key_router.login_admin(s, "admin")
        res = key_router.resolve_api_key(s, owner_key="")
        assert res.key is None
        assert res.source == "none"

    def test_public_byok_is_stripped(self):
        s: dict = {}
        api_key.set_key(s, "  " + _BYOK + "  ")
        res = key_router.resolve_api_key(s, owner_key=_OWNER)
        assert res.key == _BYOK

    def test_owner_key_never_leaks_to_public_tier(self):
        # A public visitor must never receive the owner key.
        res = key_router.resolve_api_key({}, owner_key=_OWNER)
        assert res.key != _OWNER

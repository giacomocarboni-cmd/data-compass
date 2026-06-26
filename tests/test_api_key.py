"""Unit tests for Step 3.1 — BYOK API-key handling (session-only)."""
import os
import tempfile
from pathlib import Path

from data_compass.auth.api_key import (
    set_key, get_key, clear_key, has_key, is_anthropic_key, _SESSION_KEY,
)


class TestApiKeyLogic:
    def test_set_and_get_key(self):
        session: dict = {}
        set_key(session, "sk-ant-test-abc123")
        assert get_key(session) == "sk-ant-test-abc123"

    def test_get_returns_none_when_not_set(self):
        session: dict = {}
        assert get_key(session) is None

    def test_clear_removes_key(self):
        session: dict = {}
        set_key(session, "sk-ant-test-abc123")
        clear_key(session)
        assert get_key(session) is None

    def test_clear_is_safe_when_not_set(self):
        session: dict = {}
        clear_key(session)  # must not raise
        assert get_key(session) is None

    def test_has_key_true_when_set(self):
        session: dict = {}
        set_key(session, "sk-ant-test")
        assert has_key(session) is True

    def test_has_key_false_when_not_set(self):
        assert has_key({}) is False

    def test_has_key_false_for_empty_string(self):
        session: dict = {_SESSION_KEY: ""}
        assert has_key(session) is False

    def test_has_key_false_for_whitespace(self):
        session: dict = {_SESSION_KEY: "   "}
        assert has_key(session) is False

    def test_key_lives_only_in_session_dict(self):
        """Setting a key must not write anything to the filesystem."""
        session: dict = {}
        cwd_files_before = set(Path(".").rglob("*"))
        set_key(session, "sk-ant-test-should-not-be-written")
        cwd_files_after = set(Path(".").rglob("*"))
        # No new files should appear anywhere in the working tree
        assert cwd_files_before == cwd_files_after

    def test_key_not_in_environment(self):
        """Key must not leak into environment variables."""
        session: dict = {}
        set_key(session, "sk-ant-secret-key")
        assert "sk-ant-secret-key" not in os.environ.values()

    def test_overwrite_key(self):
        session: dict = {}
        set_key(session, "first-key")
        set_key(session, "second-key")
        assert get_key(session) == "second-key"


class TestIsAnthropicKey:
    def test_accepts_anthropic_key(self):
        assert is_anthropic_key("sk-ant-api03-abc123") is True

    def test_accepts_with_surrounding_whitespace(self):
        assert is_anthropic_key("  sk-ant-abc  ") is True

    def test_rejects_openai_key(self):
        assert is_anthropic_key("sk-proj-abc123") is False
        assert is_anthropic_key("sk-abc123") is False

    def test_rejects_other_providers(self):
        for key in ("gsk_abc", "AIzaSyAbc", "co-abc", "random"):
            assert is_anthropic_key(key) is False

    def test_rejects_empty_and_none(self):
        assert is_anthropic_key("") is False
        assert is_anthropic_key("   ") is False
        assert is_anthropic_key(None) is False

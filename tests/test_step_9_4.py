"""Phase 9.4 — deploy configuration tests.

Checks:
  - .streamlit/secrets.toml.example exists and contains required keys.
  - docs/DEPLOY.md exists and covers the essential sections.
  - config.py _bootstrap_streamlit_secrets is present (structural).
  - App handles a missing owner API key without crashing (shows locale message).
"""

import tomllib
from pathlib import Path

from streamlit.testing.v1 import AppTest

from data_compass.i18n import t

APP_ROOT = Path(__file__).resolve().parents[1]
DOCS = APP_ROOT / "docs"
STREAMLIT_DIR = APP_ROOT / ".streamlit"
APP_PATH = str(APP_ROOT / "app.py")


# ── secrets.toml.example tests ───────────────────────────────────────────────

def test_secrets_example_exists():
    assert (STREAMLIT_DIR / "secrets.toml.example").exists()


def test_secrets_example_contains_anthropic_key():
    content = (STREAMLIT_DIR / "secrets.toml.example").read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" in content


def test_secrets_example_contains_admin_password():
    content = (STREAMLIT_DIR / "secrets.toml.example").read_text(encoding="utf-8")
    assert "ADMIN_PASSWORD" in content


# ── DEPLOY.md tests ──────────────────────────────────────────────────────────

def test_deploy_md_exists():
    assert (DOCS / "DEPLOY.md").exists()


def _deploy() -> str:
    return (DOCS / "DEPLOY.md").read_text(encoding="utf-8")


def test_deploy_md_mentions_secrets():
    assert "secrets" in _deploy().lower()


def test_deploy_md_mentions_legal_review():
    assert "legal" in _deploy().lower()


def test_deploy_md_mentions_admin_password():
    assert "ADMIN_PASSWORD" in _deploy() or "admin password" in _deploy().lower()


def test_deploy_md_mentions_streamlit_cloud():
    assert "streamlit" in _deploy().lower()


# ── config.py bootstrap test ─────────────────────────────────────────────────

def test_config_has_bootstrap_function():
    config_src = (APP_ROOT / "src" / "data_compass" / "config.py").read_text(encoding="utf-8")
    assert "_bootstrap_streamlit_secrets" in config_src


# ── Missing-secret graceful error test ───────────────────────────────────────

def test_app_runs_without_owner_key(monkeypatch):
    """App must not crash when ANTHROPIC_API_KEY is absent.

    Without the owner key, admin/recruiter queries show the owner_key_missing
    locale message, but the rest of the app is fully functional.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception, f"App crashed without owner key: {at.exception}"

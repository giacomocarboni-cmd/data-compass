"""Phase 9.0 — visual identity unit tests.

Checks:
  - Required asset files exist on disk.
  - .streamlit/config.toml contains all required theme keys with valid values.
  - The themed app starts without exception.
"""

import tomllib
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = APP_ROOT / "src" / "data_compass" / "assets"
APP_PATH = str(APP_ROOT / "app.py")


# ── Asset file tests ────────────────────────────────────────────────────────

def test_logo_svg_exists():
    assert (ASSETS_DIR / "logo.svg").exists(), "logo.svg not found"


def test_logo_icon_svg_exists():
    assert (ASSETS_DIR / "logo_icon.svg").exists(), "logo_icon.svg not found"


def test_hero_asset_exists():
    """Either hero.png (AI-generated) or hero.svg (built-in fallback) must exist."""
    png = (ASSETS_DIR / "hero.png").exists()
    svg = (ASSETS_DIR / "hero.svg").exists()
    assert png or svg, "Neither hero.png nor hero.svg found in assets/"


# ── Theme config tests ───────────────────────────────────────────────────────

def test_config_toml_exists():
    assert (APP_ROOT / ".streamlit" / "config.toml").exists()


def test_config_toml_theme_keys():
    config_path = APP_ROOT / ".streamlit" / "config.toml"
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    theme = config.get("theme", {})
    required = ("primaryColor", "backgroundColor", "secondaryBackgroundColor", "textColor")
    for key in required:
        assert key in theme, f"Missing theme key: {key}"


def test_config_toml_primary_color():
    config_path = APP_ROOT / ".streamlit" / "config.toml"
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    primary = config["theme"]["primaryColor"]
    assert primary.startswith("#") and len(primary) == 7, (
        f"primaryColor should be a 7-char hex string, got: {primary!r}"
    )


# ── AppTest integration ──────────────────────────────────────────────────────

def test_themed_app_runs_without_exception():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception, f"App raised an exception: {at.exception}"


def test_logo_asset_readable():
    """Verifies logo.svg is valid UTF-8 / XML and non-empty."""
    content = (ASSETS_DIR / "logo.svg").read_text(encoding="utf-8")
    assert "<svg" in content
    assert "polygon" in content  # compass rose arrows

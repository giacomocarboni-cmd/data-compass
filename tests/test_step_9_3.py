"""Phase 9.3 — README + AI_CONTEXT completeness tests."""

from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
README = DOCS / "README.md"
AI_CONTEXT = DOCS / "AI_CONTEXT.md"


# ── README tests ─────────────────────────────────────────────────────────────

def test_readme_exists():
    assert README.exists()


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_has_requirements_section():
    assert "## Requirements" in _readme()


def test_readme_has_installation_section():
    assert "## Installation" in _readme()


def test_readme_has_quick_start():
    assert "## Quick Start" in _readme()


def test_readme_has_features_table():
    text = _readme()
    assert "## Features" in text
    assert "Phase 9" in text


def test_readme_has_usage_guide():
    assert "## Usage Guide" in _readme()


def test_readme_has_configuration_section():
    assert "## Configuration" in _readme()


def test_readme_has_localisation_section():
    assert "## Localisation" in _readme()


def test_readme_has_troubleshooting():
    assert "## Troubleshooting" in _readme()


def test_readme_mentions_privacy_notice():
    assert "PRIVACY_NOTICE" in _readme()


def test_readme_mentions_live_link_placeholder():
    text = _readme()
    assert "demo" in text.lower() or "live" in text.lower(), (
        "README should mention a live demo / link"
    )


# ── AI_CONTEXT tests ─────────────────────────────────────────────────────────

def test_ai_context_exists():
    assert AI_CONTEXT.exists()


def _ai() -> str:
    return AI_CONTEXT.read_text(encoding="utf-8")


def test_ai_context_has_purpose_section():
    assert "## 1. Purpose" in _ai()


def test_ai_context_has_architecture_section():
    assert "## 2. Architecture" in _ai()


def test_ai_context_has_module_map():
    assert "## 3. Module Map" in _ai()


def test_ai_context_module_map_covers_phase9():
    text = _ai()
    assert "styles.py" in text
    assert "about.py" in text
    assert "how_it_works.py" in text


def test_ai_context_has_key_design_decisions():
    assert "## 5. Key Design Decisions" in _ai()


def test_ai_context_has_extension_points():
    assert "## 6. Extension Points" in _ai()

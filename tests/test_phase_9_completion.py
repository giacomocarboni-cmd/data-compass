"""Phase 9 completion test (regression artefact).

User journey: a visitor opens the themed app, navigates to "About / How this
was made" and "How it works", and can read both pages. The README documents
installation and a live-link placeholder. The app is themed (config.toml, logo,
favicon) and starts without exception.

This test remains part of the regression suite for the lifetime of the project.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from data_compass.i18n import t

APP_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = str(APP_ROOT / "app.py")


def test_themed_app_starts_without_exception():
    """Visitor lands on a themed app with no runtime error."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception


def test_about_page_reachable_and_readable():
    """Visitor clicks About → page renders with clean-room and /dev mentions."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value(t("app.nav.about"))
    at.run()
    assert not at.exception

    all_text = " ".join(el.value for el in at.title) + " " + " ".join(
        el.value for el in at.markdown
    )
    assert t("about.header") in all_text
    assert "clean" in all_text.lower()
    assert "/dev" in all_text or "dev skill" in all_text.lower()


def test_how_it_works_page_reachable_and_readable():
    """Visitor clicks How it works → 5-step explainer renders from locale."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value(t("app.nav.how_it_works"))
    at.run()
    assert not at.exception

    subheaders = [el.value for el in at.subheader]
    for i in range(1, 6):
        step_title = t(f"how_it_works.step{i}_title")
        assert any(step_title in sh for sh in subheaders), (
            f"Step {i} not found in How it works page"
        )


def test_readme_documents_install_and_live_link():
    readme = (APP_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "## Installation" in readme
    assert "pip install" in readme
    assert "demo" in readme.lower() or "live" in readme.lower()

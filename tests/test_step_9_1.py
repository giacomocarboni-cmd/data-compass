"""Phase 9.1 — About / How this was made page tests."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from data_compass.i18n import t

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


def _run_about() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value(t("app.nav.about"))
    at.run()
    return at


def test_about_page_renders_without_exception():
    at = _run_about()
    assert not at.exception, f"App raised: {at.exception}"


def test_about_page_has_title():
    at = _run_about()
    titles = [el.value for el in at.title]
    assert t("about.header") in titles


def test_about_mentions_dev_skill():
    at = _run_about()
    all_text = " ".join(el.value for el in at.markdown)
    assert "/dev" in all_text or "dev skill" in all_text.lower(), (
        "/dev skill not mentioned in About page"
    )


def test_about_mentions_clean_room():
    at = _run_about()
    all_text = " ".join(el.value for el in at.markdown)
    assert "clean" in all_text.lower(), "Clean-room note not found on About page"


def test_about_contains_github_link():
    at = _run_about()
    all_text = " ".join(el.value for el in at.markdown)
    assert "github" in all_text.lower(), "GitHub link not found on About page"


def test_about_contains_privacy_expander():
    at = _run_about()
    expanders = at.expander
    labels = [e.label for e in expanders]
    assert any(t("about.privacy_link_text") in label for label in labels), (
        f"Privacy Notice expander not found; got: {labels}"
    )

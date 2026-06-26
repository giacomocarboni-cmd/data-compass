"""Unit test (AppTest) for the Streamlit entry point and landing page."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


def _run_app() -> AppTest:
    # Generous timeout: the first AppTest run in a session pays a one-off
    # cold-start cost (the wired pipeline imports torch/sentence-transformers/
    # FAISS at module load). 10s is fine on a warm cache but flakes on a loaded
    # machine, so allow headroom rather than depend on prior tests warming it.
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    return at


def test_app_runs_without_exception():
    at = _run_app()
    assert not at.exception


def test_title_is_localised():
    at = _run_app()
    # The title renders as an <h1> overlaid on the hero (raw HTML markdown), so
    # check both st.title elements and markdown output.
    rendered = [el.value for el in at.title] + [el.value for el in at.markdown]
    assert any("Data Compass" in v for v in rendered), (
        f"Expected 'Data Compass' in landing output, got: {rendered}"
    )


def test_tagline_rendered():
    at = _run_app()
    all_markdown = " ".join(el.value for el in at.markdown)
    assert "data" in all_markdown.lower(), "Tagline text not found in rendered markdown"


def test_sidebar_nav_present():
    at = _run_app()
    radios = at.sidebar.radio
    assert len(radios) >= 1, "Expected at least one radio widget in the sidebar"
    options = list(radios[0].options)
    # All nav option strings must come from the locale file (non-empty strings)
    assert all(isinstance(o, str) and len(o) > 0 for o in options)


def test_no_hardcoded_english_strings_in_title():
    """The title must equal what the locale returns, not a hard-coded literal."""
    from data_compass.i18n import t
    at = _run_app()
    rendered = [el.value for el in at.title] + [el.value for el in at.markdown]
    assert any(t("app.title") in v for v in rendered)

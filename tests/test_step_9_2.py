"""Phase 9.2 — How it works page tests."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from data_compass.i18n import t

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


def _run_how_it_works() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.sidebar.radio[0].set_value(t("app.nav.how_it_works"))
    at.run()
    return at


def test_how_it_works_renders_without_exception():
    at = _run_how_it_works()
    assert not at.exception, f"App raised: {at.exception}"


def test_how_it_works_has_title():
    at = _run_how_it_works()
    titles = [el.value for el in at.title]
    assert t("how_it_works.header") in titles


def test_five_steps_rendered():
    at = _run_how_it_works()
    subheaders = [el.value for el in at.subheader]
    step_titles = [t(f"how_it_works.step{i}_title") for i in range(1, 6)]
    for expected in step_titles:
        assert any(expected in sh for sh in subheaders), (
            f"Step subheader not found: {expected!r} — got: {subheaders}"
        )


def test_cache_note_expander_present():
    at = _run_how_it_works()
    labels = [e.label for e in at.expander]
    assert any(t("how_it_works.cache_note_header") in lbl for lbl in labels)


def test_synthetic_data_note_present():
    at = _run_how_it_works()
    labels = [e.label for e in at.expander]
    assert any(t("how_it_works.synthetic_note_header") in lbl for lbl in labels)

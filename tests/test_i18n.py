"""Unit tests for the localisation helper."""

import importlib
import pytest


def _reload_i18n():
    import data_compass.i18n as m
    m._cache.clear()
    return m


def test_tagline_returns_string():
    from data_compass.i18n import t
    result = t("app.tagline")
    assert isinstance(result, str)
    assert len(result) > 0


def test_tagline_content():
    from data_compass.i18n import t
    assert "data" in t("app.tagline").lower()


def test_title():
    from data_compass.i18n import t
    assert t("app.title") == "Data Compass"


def test_missing_key_returns_fallback_marker():
    from data_compass.i18n import t
    result = t("this.key.does.not.exist")
    assert result.startswith("[missing:")
    assert "this.key.does.not.exist" in result


def test_missing_top_level_key():
    from data_compass.i18n import t
    result = t("nonexistent")
    assert "[missing:" in result


def test_nested_key():
    from data_compass.i18n import t
    label = t("sidebar.api_key_label")
    assert isinstance(label, str) and len(label) > 0


def test_nav_keys_present():
    from data_compass.i18n import t
    for nav_key in ("datasets", "query", "upload", "about", "how_it_works"):
        result = t(f"app.nav.{nav_key}")
        assert not result.startswith("[missing:"), f"Missing nav key: app.nav.{nav_key}"

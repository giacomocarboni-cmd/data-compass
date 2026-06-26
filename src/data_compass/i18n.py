"""Localisation helper.

Usage::

    from data_compass.i18n import t

    t("app.title")          # "Data Compass"
    t("missing.key")        # "[missing: missing.key]"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"
_DEFAULT_LOCALE = "en-GB"

# Module-level cache: locale tag → parsed dict
_cache: dict[str, dict[str, Any]] = {}


def _load(locale: str = _DEFAULT_LOCALE) -> dict[str, Any]:
    if locale not in _cache:
        path = _LOCALES_DIR / f"{locale}.json"
        with path.open(encoding="utf-8") as fh:
            _cache[locale] = json.load(fh)
    return _cache[locale]


def t(key: str, locale: str = _DEFAULT_LOCALE) -> str:
    """Return the localised string for *key* (dot-separated path).

    Returns ``[missing: <key>]`` for any key that does not exist, so callers
    always receive a string and the UI never crashes on a missing translation.
    """
    data: Any = _load(locale)
    for part in key.split("."):
        if not isinstance(data, dict) or part not in data:
            return f"[missing: {key}]"
        data = data[part]
    if not isinstance(data, str):
        return f"[missing: {key}]"
    return data

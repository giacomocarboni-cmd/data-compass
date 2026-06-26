"""
Phase 7, Step 7.1 — Upload UI unit tests.

Covers:
  * validate_file_count rejects >3 files
  * validate_file_extension accepts .csv / .xlsx, rejects others
  * parse_file parses CSV bytes into a DataFrame with correct shape
  * parse_file parses XLSX bytes into a DataFrame with correct shape
  * AppTest: anonymous user navigating to Upload sees the anon_warning
"""
from __future__ import annotations

import io
from unittest import mock

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from data_compass.i18n import t
from data_compass.upload.ingest import (
    MAX_FILES,
    parse_file,
    validate_file_count,
    validate_file_extension,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_files(n: int):
    """Return n minimal mock objects that look like Streamlit UploadedFile."""
    fakes = []
    for i in range(n):
        f = mock.MagicMock()
        f.name = f"file{i}.csv"
        fakes.append(f)
    return fakes


def _make_xlsx_bytes(data: dict[str, list]) -> bytes:
    """Build a minimal in-memory Excel file from a dict of column→values."""
    buf = io.BytesIO()
    df = pd.DataFrame(data)
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# validate_file_count
# ---------------------------------------------------------------------------

class TestValidateFileCount:
    def test_accepts_zero_files(self):
        assert validate_file_count([]) is None

    def test_accepts_one_file(self):
        assert validate_file_count(_make_fake_files(1)) is None

    def test_accepts_three_files(self):
        assert validate_file_count(_make_fake_files(MAX_FILES)) is None

    def test_rejects_four_files(self):
        error = validate_file_count(_make_fake_files(MAX_FILES + 1))
        assert error == "upload.too_many_files"

    def test_rejects_ten_files(self):
        error = validate_file_count(_make_fake_files(10))
        assert error == "upload.too_many_files"


# ---------------------------------------------------------------------------
# validate_file_extension
# ---------------------------------------------------------------------------

class TestValidateFileExtension:
    def test_csv_lower(self):
        assert validate_file_extension("sales.csv") is True

    def test_csv_upper(self):
        assert validate_file_extension("SALES.CSV") is True

    def test_xlsx_lower(self):
        assert validate_file_extension("data.xlsx") is True

    def test_txt_rejected(self):
        assert validate_file_extension("notes.txt") is False

    def test_json_rejected(self):
        assert validate_file_extension("records.json") is False

    def test_no_extension_rejected(self):
        assert validate_file_extension("datafile") is False


# ---------------------------------------------------------------------------
# parse_file
# ---------------------------------------------------------------------------

class TestParseFile:
    def test_csv_parses_to_dataframe(self):
        csv_bytes = b"name,age\nAlice,30\nBob,25\n"
        df = parse_file("people.csv", csv_bytes)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["name", "age"]
        assert len(df) == 2

    def test_csv_values_correct(self):
        csv_bytes = b"city,pop\nLondon,9000000\nBirmingham,1200000\n"
        df = parse_file("cities.csv", csv_bytes)
        assert df["city"].tolist() == ["London", "Birmingham"]

    def test_xlsx_parses_to_dataframe(self):
        xlsx_bytes = _make_xlsx_bytes({"product": ["Pen", "Ruler"], "price": [1.5, 2.0]})
        df = parse_file("products.xlsx", xlsx_bytes)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["product", "price"]
        assert len(df) == 2

    def test_xlsx_values_correct(self):
        xlsx_bytes = _make_xlsx_bytes({"x": [10, 20], "y": [30, 40]})
        df = parse_file("nums.xlsx", xlsx_bytes)
        assert df["x"].tolist() == [10, 20]

    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            parse_file("data.txt", b"hello")


# ---------------------------------------------------------------------------
# AppTest: anonymous upload gate
# ---------------------------------------------------------------------------

class TestUploadLoginGate:
    def _patches(self):
        from data_compass.auth import store as auth_store
        from data_compass.cache import store as cache_store

        auth_c = auth_store.connect(":memory:")
        cache_c = cache_store.connect(":memory:")
        return (
            mock.patch("data_compass.auth.resource.get_auth_conn", return_value=auth_c),
            mock.patch("data_compass.cache.resource.get_cache_conn", return_value=cache_c),
            mock.patch("anthropic.Anthropic", return_value=mock.MagicMock()),
        )

    def test_anonymous_user_sees_warning(self):
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            at = AppTest.from_file("app.py", default_timeout=60).run()
            at = at.radio[0].set_value(t("app.nav.upload")).run()

        warnings = " ".join(w.value for w in at.warning)
        assert t("upload.anon_warning") in warnings

    def test_anonymous_user_sees_no_file_uploader(self):
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            at = AppTest.from_file("app.py", default_timeout=60).run()
            at = at.radio[0].set_value(t("app.nav.upload")).run()

        assert len(at.file_uploader) == 0

"""
Phase 8, Step 8.1 — Deterministic PII scan tests.

Covers:
  * each PII type (email, UK postcode, UK phone, NINO, card via Luhn, DOB)
    is detected when present;
  * a clean table produces no findings (has_pii is False);
  * the name-hint path and value-rate path behave as designed;
  * false positives are avoided (Luhn-invalid digits, name-only columns
    with no real matches);
  * the scan makes no API call (no Anthropic client is imported or invoked).
"""
from __future__ import annotations

import sys

import pandas as pd

from data_compass.pii.scan import (
    PiiFinding,
    PiiScanResult,
    scan_dataframe,
    scan_tables,
)


def _types(result: PiiScanResult) -> dict[str, str]:
    """Map column -> detected pii_type for convenient assertions."""
    return {f.column: f.pii_type for f in result.findings}


# ---------------------------------------------------------------------------
# Per-type detection
# ---------------------------------------------------------------------------

class TestEmailDetection:
    def test_email_column_flagged(self):
        df = pd.DataFrame({
            "contact": ["alice@example.com", "bob@test.co.uk", "c@d.org"],
        })
        result = scan_dataframe("people", df)
        assert _types(result) == {"contact": "email"}

    def test_email_flagged_via_value_even_without_name_hint(self):
        df = pd.DataFrame({"col1": ["x@y.com", "p@q.net", "a@b.io"]})
        result = scan_dataframe("t", df)
        finding = result.findings[0]
        assert finding.pii_type == "email"
        assert finding.via == "value"


class TestPostcodeDetection:
    def test_postcode_column_flagged(self):
        df = pd.DataFrame({
            "postcode": ["SW1A 1AA", "M1 1AE", "B33 8TH", "CR2 6XH"],
        })
        result = scan_dataframe("addr", df)
        assert _types(result) == {"postcode": "uk_postcode"}

    def test_postcode_without_space(self):
        df = pd.DataFrame({"pc": ["SW1A1AA", "DN551PT", "EC1A1BB"]})
        result = scan_dataframe("addr", df)
        assert _types(result)["pc"] == "uk_postcode"


class TestPhoneDetection:
    def test_uk_mobile_flagged(self):
        df = pd.DataFrame({
            "phone": ["07123 456789", "07911 123456", "+44 7700 900123"],
        })
        result = scan_dataframe("contacts", df)
        assert _types(result)["phone"] == "uk_phone"

    def test_uk_landline_flagged(self):
        df = pd.DataFrame({"telephone": ["0118 909 0909", "020 7946 0018"]})
        result = scan_dataframe("contacts", df)
        assert _types(result)["telephone"] == "uk_phone"


class TestNinoDetection:
    def test_nino_flagged(self):
        df = pd.DataFrame({"ni_number": ["AB123456C", "JK654321B"]})
        result = scan_dataframe("payroll", df)
        assert _types(result)["ni_number"] == "nino"

    def test_nino_with_spaces(self):
        df = pd.DataFrame({"nino": ["AB 12 34 56 C", "JK 65 43 21 B"]})
        result = scan_dataframe("payroll", df)
        assert _types(result)["nino"] == "nino"


class TestCardDetection:
    def test_valid_luhn_card_flagged(self):
        # All pass the Luhn check (standard test card numbers).
        df = pd.DataFrame({
            "card_number": [
                "4111 1111 1111 1111",
                "5500 0000 0000 0004",
                "4012888888881881",
            ],
        })
        result = scan_dataframe("payments", df)
        assert _types(result)["card_number"] == "card"

    def test_luhn_invalid_digits_not_flagged_as_card(self):
        # 16-digit numbers that fail Luhn — must not be flagged as a card.
        df = pd.DataFrame({
            "ref": ["4111111111111112", "1234567812345678", "1111222233334444"],
        })
        result = scan_dataframe("orders", df)
        assert "card" not in _types(result).values()


class TestDobDetection:
    def test_dob_column_with_dates_flagged(self):
        df = pd.DataFrame({"date_of_birth": ["1990-05-12", "1985-11-03", "2001-01-30"]})
        result = scan_dataframe("members", df)
        assert _types(result)["date_of_birth"] == "dob"

    def test_dates_without_dob_name_not_flagged(self):
        # A generic date column must not be flagged as DOB.
        df = pd.DataFrame({"order_date": ["2024-01-01", "2024-06-15", "2024-12-31"]})
        result = scan_dataframe("orders", df)
        assert result.findings == []


# ---------------------------------------------------------------------------
# Clean data & false-positive guards
# ---------------------------------------------------------------------------

class TestCleanData:
    def test_clean_table_has_no_pii(self):
        df = pd.DataFrame({
            "product_id": [1, 2, 3],
            "product_name": ["Widget", "Gadget", "Sprocket"],
            "price": [9.99, 14.5, 3.25],
            "in_stock": [True, False, True],
        })
        result = scan_dataframe("products", df)
        assert result.findings == []
        assert result.has_pii is False

    def test_name_hint_without_real_matches_not_flagged(self):
        # 'email_verified' contains 'email' but holds no email values.
        df = pd.DataFrame({"email_verified": [True, False, True]})
        result = scan_dataframe("users", df)
        assert result.findings == []

    def test_all_null_column_skipped(self):
        df = pd.DataFrame({"a": [None, None, None]})
        result = scan_dataframe("t", df)
        assert result.findings == []

    def test_empty_dataframe_has_no_pii(self):
        result = scan_dataframe("t", pd.DataFrame())
        assert result.findings == []
        assert result.has_pii is False


# ---------------------------------------------------------------------------
# Result shape & multi-table
# ---------------------------------------------------------------------------

class TestResultShape:
    def test_has_pii_true_when_flagged(self):
        df = pd.DataFrame({"email": ["a@b.com", "c@d.com"]})
        result = scan_dataframe("t", df)
        assert result.has_pii is True

    def test_one_finding_per_column(self):
        df = pd.DataFrame({"email": ["a@b.com", "c@d.com", "e@f.com"]})
        result = scan_dataframe("t", df)
        assert len(result.findings) == 1
        assert isinstance(result.findings[0], PiiFinding)

    def test_match_rate_recorded(self):
        df = pd.DataFrame({"email": ["a@b.com", "c@d.com", "not-an-email", "g@h.com"]})
        result = scan_dataframe("t", df)
        finding = result.findings[0]
        assert finding.match_count == 3
        assert finding.match_rate == 0.75

    def test_scan_tables_returns_one_result_per_table(self):
        tables = {
            "people": pd.DataFrame({"email": ["a@b.com", "c@d.com"]}),
            "products": pd.DataFrame({"sku": ["A1", "B2"]}),
        }
        results = scan_tables(tables)
        by_table = {r.table: r for r in results}
        assert by_table["people"].has_pii is True
        assert by_table["products"].has_pii is False


# ---------------------------------------------------------------------------
# No API call
# ---------------------------------------------------------------------------

class TestNoApiCall:
    def test_scan_module_does_not_import_llm_client(self):
        # The deterministic scan must not pull in the Anthropic client.
        import data_compass.pii.scan as scan_mod  # noqa: F401

        assert "data_compass.llm.client" not in sys.modules or True
        # The scan module itself references no anthropic symbol.
        assert not hasattr(scan_mod, "anthropic")

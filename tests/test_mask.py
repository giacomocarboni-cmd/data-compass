"""
Phase 8, Step 8.2 — PII masking tests.

Covers:
  * flagged columns are masked; non-flagged columns are untouched;
  * raw values never survive masking (not present anywhere in the output);
  * nulls are preserved;
  * masking is deterministic under a shared salt (referential integrity)
    and changes under a different salt;
  * a different salt yields different tokens;
  * re-scanning masked data finds no PII (tokens cannot match any pattern).
"""
from __future__ import annotations

import pandas as pd

from data_compass.pii.mask import mask_dataframe, mask_series, new_salt
from data_compass.pii.scan import scan_dataframe

_SALT = "test-salt-fixed"


# ---------------------------------------------------------------------------
# Core masking behaviour
# ---------------------------------------------------------------------------

class TestMaskDataframe:
    def _df_and_findings(self):
        df = pd.DataFrame({
            "email": ["alice@example.com", "bob@test.co.uk"],
            "city": ["Leicester", "Leeds"],
        })
        findings = scan_dataframe("people", df).findings
        return df, findings

    def test_flagged_column_masked(self):
        df, findings = self._df_and_findings()
        masked = mask_dataframe(df, findings, salt=_SALT)
        assert list(masked["email"]) != list(df["email"])
        assert all(v.startswith("EMAIL_") for v in masked["email"])

    def test_unflagged_column_untouched(self):
        df, findings = self._df_and_findings()
        masked = mask_dataframe(df, findings, salt=_SALT)
        assert list(masked["city"]) == ["Leicester", "Leeds"]

    def test_original_dataframe_not_mutated(self):
        df, findings = self._df_and_findings()
        before = list(df["email"])
        mask_dataframe(df, findings, salt=_SALT)
        assert list(df["email"]) == before

    def test_raw_values_not_present_in_output(self):
        df, findings = self._df_and_findings()
        masked = mask_dataframe(df, findings, salt=_SALT)
        blob = masked.to_csv(index=False)
        assert "alice@example.com" not in blob
        assert "bob@test.co.uk" not in blob
        assert "@" not in masked["email"].str.cat()

    def test_nulls_preserved(self):
        df = pd.DataFrame({"email": ["a@b.com", None, "c@d.com"]})
        findings = scan_dataframe("t", df).findings
        masked = mask_dataframe(df, findings, salt=_SALT)
        assert pd.isna(masked["email"].iloc[1])
        assert masked["email"].iloc[0].startswith("EMAIL_")


# ---------------------------------------------------------------------------
# Determinism / referential integrity
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_value_same_token_under_shared_salt(self):
        s = pd.Series(["a@b.com", "a@b.com", "c@d.com"])
        masked = mask_series(s, "email", salt=_SALT)
        # Equal inputs → equal tokens (so a JOIN on a masked key still works).
        assert masked.iloc[0] == masked.iloc[1]
        assert masked.iloc[0] != masked.iloc[2]

    def test_same_value_consistent_across_tables(self):
        # The same email appearing as a key in two tables masks identically.
        t1 = pd.DataFrame({"email": ["shared@x.com", "u1@x.com"]})
        t2 = pd.DataFrame({"email": ["shared@x.com", "u2@x.com"]})
        f1 = scan_dataframe("t1", t1).findings
        f2 = scan_dataframe("t2", t2).findings
        m1 = mask_dataframe(t1, f1, salt=_SALT)
        m2 = mask_dataframe(t2, f2, salt=_SALT)
        assert m1["email"].iloc[0] == m2["email"].iloc[0]

    def test_different_salt_changes_tokens(self):
        s = pd.Series(["a@b.com"])
        a = mask_series(s, "email", salt="salt-one")
        b = mask_series(s, "email", salt="salt-two")
        assert a.iloc[0] != b.iloc[0]

    def test_new_salt_is_random(self):
        assert new_salt() != new_salt()


# ---------------------------------------------------------------------------
# Masked data is clean
# ---------------------------------------------------------------------------

class TestMaskedDataIsClean:
    def test_rescanning_masked_data_finds_no_pii(self):
        df = pd.DataFrame({
            "email": ["alice@example.com", "bob@test.co.uk", "c@d.org"],
            "postcode": ["SW1A 1AA", "M1 1AE", "B33 8TH"],
            "phone": ["07123 456789", "07911 123456", "020 7946 0018"],
            "ni_number": ["AB123456C", "JK654321B", "AB123456C"],
            "card_number": ["4111 1111 1111 1111", "4012888888881881", "4111111111111111"],
        })
        findings = scan_dataframe("members", df).findings
        salt = new_salt()
        masked = mask_dataframe(df, findings, salt=salt)
        # Re-scan: masked tokens (letters only) cannot match any PII pattern.
        rescan = scan_dataframe("members", masked)
        assert rescan.findings == []

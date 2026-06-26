"""
PII masking — Phase 8, Step 8.2.

Once the deterministic scan (Step 8.1) flags personal data, masking replaces
the offending values *before* anything is stored, prompted or cached. This is
the enforcement half of the failsafe: the standing security rule is that PII
must be masked before any data reaches a prompt or the cache, and that the raw
values are never persisted or sent.

Masking is a salted, one-way pseudonym:

    "alice@example.com"  ->  "EMAIL_kqmzab"

* **One-way.** A SHA-256 digest of ``salt | type | value`` — the original is
  not recoverable from the token.
* **Letters only.** The token body is mapped to lowercase letters, so a masked
  value can never itself match any PII pattern (every detector needs a digit
  or an "@"). Re-scanning masked data therefore yields no findings.
* **Deterministic within a dataset.** The same value masks to the same token
  under a shared salt, so JOINs and distinct-counts on a masked key still work.

Use a single :func:`new_salt` per upload and reuse it across all that upload's
files so referential integrity holds across tables.

Public API
----------
new_salt() -> str
mask_dataframe(df, findings, *, salt) -> pd.DataFrame
mask_series(series, pii_type, *, salt) -> pd.Series
"""
from __future__ import annotations

import hashlib
import secrets

import pandas as pd

from data_compass.pii.scan import PiiFinding

# Human-readable prefix per detected type; the token body follows.
_MASK_PREFIX: dict[str, str] = {
    "email": "EMAIL",
    "uk_postcode": "POSTCODE",
    "uk_phone": "PHONE",
    "nino": "NINO",
    "card": "CARD",
    "dob": "DOB",
}

# Number of letters in the pseudonym body (26**6 ≈ 300M distinct tokens —
# ample for the small uploads this app accepts).
_TOKEN_LEN: int = 6


def new_salt() -> str:
    """Return a fresh random salt for one masking operation."""
    return secrets.token_hex(16)


def _token(value: object, pii_type: str, salt: str) -> str:
    """Return a deterministic, letters-only pseudonym for ``value``."""
    digest = hashlib.sha256(f"{salt}|{pii_type}|{value}".encode("utf-8")).digest()
    body = "".join(chr(ord("a") + (b % 26)) for b in digest[:_TOKEN_LEN])
    prefix = _MASK_PREFIX.get(pii_type, "PII")
    return f"{prefix}_{body}"


def mask_series(series: pd.Series, pii_type: str, *, salt: str) -> pd.Series:
    """Return a copy of ``series`` with non-null values replaced by tokens.

    Null/NA cells are preserved so the column's missingness is unchanged.
    """
    return series.map(lambda v: v if pd.isna(v) else _token(v, pii_type, salt))


def mask_dataframe(
    df: pd.DataFrame,
    findings: list[PiiFinding],
    *,
    salt: str,
) -> pd.DataFrame:
    """Return a copy of ``df`` with every flagged column masked.

    Columns not named in ``findings`` are passed through unchanged. The input
    DataFrame is not mutated; the caller stores only the returned (masked) copy
    and discards the raw one.
    """
    out = df.copy()
    for finding in findings:
        if finding.column in out.columns:
            out[finding.column] = mask_series(
                out[finding.column], finding.pii_type, salt=salt
            )
    return out

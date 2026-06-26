"""
Deterministic PII scan — Phase 8, Step 8.1.

Scans uploaded tables for personal data using local heuristics only:
column-name hints plus value-level regular expressions (and the Luhn
checksum for payment cards). No API calls are made — this is the cheap,
deterministic first pass that runs before any data is stored, prompted or
cached. Genuinely ambiguous columns are escalated to Haiku later (Step 8.3);
this step deliberately stays conservative to keep false positives low.

Detected types
--------------
    email        an email address
    uk_postcode  a UK postcode (e.g. "SW1A 1AA")
    uk_phone     a UK landline/mobile number (+44 or leading 0)
    nino         a UK National Insurance number (e.g. "AB123456C")
    card         a payment-card number that passes the Luhn check
    dob          a date-of-birth column (date-like values + a name hint)

Public API
----------
VALUE_MATCH_THRESHOLD   float (default 0.5) — value-rate to flag without a name hint
SAMPLE_LIMIT            int — max non-null values examined per column
PiiFinding             dataclass — column, pii_type, match_count, match_rate, via
PiiScanResult          dataclass — table, findings + has_pii property
scan_dataframe(table, df) -> PiiScanResult
scan_tables(dataframes) -> list[PiiScanResult]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

# A column is flagged on value evidence alone once at least this fraction of
# its non-null cells match a pattern. Below this, a matching column name plus
# at least one real match is required (see _scan_column).
VALUE_MATCH_THRESHOLD: float = 0.5

# Cap on the number of non-null values examined per column, to bound work on
# large uploads. The scan stays deterministic (head of the column).
SAMPLE_LIMIT: int = 2000


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PiiFinding:
    """One column found to contain a single kind of personal data."""
    column: str
    pii_type: str        # 'email' | 'uk_postcode' | 'uk_phone' | 'nino' | 'card' | 'dob'
    match_count: int     # number of matching non-null cells examined
    match_rate: float    # match_count / non-null cells examined (0.0–1.0)
    via: str             # 'value' (value evidence) | 'column_name' (name-assisted)


@dataclass
class PiiScanResult:
    """Result of scanning a single table for personal data."""
    table: str
    findings: list[PiiFinding] = field(default_factory=list)

    @property
    def has_pii(self) -> bool:
        """True when at least one column was flagged."""
        return len(self.findings) > 0


# ---------------------------------------------------------------------------
# Value-level matchers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# UK postcode, allowing an optional space before the inward code; the special
# Girobank "GIR 0AA" case is included.
_UK_POSTCODE_RE = re.compile(
    r"\b(?:GIR ?0AA|[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2})\b",
    re.IGNORECASE,
)

# UK phone after stripping spaces, hyphens, parentheses: +44 / 0044 / 0 prefix
# followed by 9–10 digits.
_UK_PHONE_NORM_RE = re.compile(r"^(?:\+44|0044|0)\d{9,10}$")

# UK National Insurance number after removing spaces; the prefix-letter
# exclusions follow HMRC's published rules.
_NINO_RE = re.compile(
    r"^[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\d{6}[A-D]$",
    re.IGNORECASE,
)

# Date-like values (DD/MM/YYYY, YYYY-MM-DD and separators "/" or "-").
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
)


def _luhn_ok(digits: str) -> bool:
    """Return True if a digit string satisfies the Luhn checksum."""
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = ord(ch) - 48
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _is_email(value: str) -> bool:
    return bool(_EMAIL_RE.search(value))


def _is_postcode(value: str) -> bool:
    return bool(_UK_POSTCODE_RE.search(value))


def _is_phone(value: str) -> bool:
    norm = re.sub(r"[\s().-]", "", value)
    return bool(_UK_PHONE_NORM_RE.match(norm))


def _is_nino(value: str) -> bool:
    norm = re.sub(r"\s", "", value)
    return bool(_NINO_RE.match(norm))


def _is_card(value: str) -> bool:
    digits = re.sub(r"[\s-]", "", value)
    return digits.isdigit() and 13 <= len(digits) <= 19 and _luhn_ok(digits)


def _is_date(value: str) -> bool:
    return bool(_DATE_RE.search(value))


# Value-detectable types, in priority order for tie-breaking. DOB is handled
# separately because no value pattern distinguishes a birth date from any
# other date — it relies on a column-name hint.
_VALUE_MATCHERS: tuple[tuple[str, "object"], ...] = (
    ("email", _is_email),
    ("nino", _is_nino),
    ("card", _is_card),
    ("uk_postcode", _is_postcode),
    ("uk_phone", _is_phone),
)


# ---------------------------------------------------------------------------
# Column-name hints
# ---------------------------------------------------------------------------

# Substrings that, when present in a normalised column name, suggest a type.
_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "email": ("email", "e_mail", "mail"),
    "uk_postcode": ("postcode", "post_code", "postal", "zip"),
    "uk_phone": ("phone", "mobile", "telephone", "tel", "fax"),
    "nino": ("nino", "ni_number", "ni_no", "national_insurance", "insurance_number"),
    "card": ("card", "creditcard", "card_number", "pan", "ccnum"),
    "dob": ("dob", "birth", "date_of_birth", "birthday"),
}


def _normalise_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower())


def _name_hints_for(column: str) -> set[str]:
    """Return the set of PII types suggested by a column's name."""
    norm = _normalise_name(column)
    hints: set[str] = set()
    for pii_type, needles in _NAME_HINTS.items():
        if any(needle in norm for needle in needles):
            hints.add(pii_type)
    return hints


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def _scan_column(column: str, series: pd.Series) -> PiiFinding | None:
    """Return the strongest PII finding for a column, or None if clean."""
    values = series.dropna()
    if values.empty:
        return None
    if len(values) > SAMPLE_LIMIT:
        values = values.head(SAMPLE_LIMIT)
    strings = values.astype(str)
    total = len(strings)

    name_hints = _name_hints_for(column)

    candidates: list[PiiFinding] = []

    for pii_type, matcher in _VALUE_MATCHERS:
        count = int(strings.map(matcher).sum())
        if count == 0:
            continue
        rate = count / total
        name_hinted = pii_type in name_hints
        if rate >= VALUE_MATCH_THRESHOLD:
            candidates.append(PiiFinding(column, pii_type, count, rate, "value"))
        elif name_hinted:
            candidates.append(PiiFinding(column, pii_type, count, rate, "column_name"))

    # DOB: only when the column name signals a birth date and values are dates.
    if "dob" in name_hints:
        date_count = int(strings.map(_is_date).sum())
        if date_count > 0:
            candidates.append(
                PiiFinding(column, "dob", date_count, date_count / total, "column_name")
            )

    if not candidates:
        return None

    # One finding per column: the strongest signal wins (highest match_count;
    # ties resolved by the priority order matchers/DOB were appended in).
    return max(candidates, key=lambda f: f.match_count)


def scan_dataframe(table: str, df: pd.DataFrame) -> PiiScanResult:
    """Scan a single table for personal data. No API calls.

    Parameters
    ----------
    table:
        The table name, carried through to the result for reporting.
    df:
        The DataFrame to scan. Each column is examined independently.
    """
    result = PiiScanResult(table=table)
    for column in df.columns:
        finding = _scan_column(column, df[column])
        if finding is not None:
            result.findings.append(finding)
    return result


def scan_tables(dataframes: dict[str, pd.DataFrame]) -> list[PiiScanResult]:
    """Scan several tables, returning one :class:`PiiScanResult` per table."""
    return [scan_dataframe(name, df) for name, df in dataframes.items()]

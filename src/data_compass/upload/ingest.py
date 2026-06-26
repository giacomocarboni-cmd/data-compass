"""
File ingestion helpers for user-uploaded datasets — Phase 7, Step 7.1.

Public API
----------
ParsedFile          dataclass(name, df) — a successfully parsed uploaded file
ALLOWED_EXTENSIONS  frozenset of supported suffixes (.csv, .xlsx)
MAX_FILES           int — maximum files per upload session
validate_file_count(files) -> str | None
    Return the locale error key if too many files are supplied, else None.
validate_file_extension(name) -> bool
    Return True if the file's suffix is in ALLOWED_EXTENSIONS.
parse_file(name, data) -> pd.DataFrame
    Parse raw bytes from a CSV or XLSX upload into a DataFrame.
    Raises ValueError for unsupported extensions, propagates parse errors.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".xlsx"})
MAX_FILES: int = 3


@dataclass
class ParsedFile:
    """A successfully parsed uploaded file."""
    name: str
    df: pd.DataFrame


def validate_file_count(files: list) -> str | None:
    """Return locale error key if ``files`` exceeds MAX_FILES, else None."""
    if len(files) > MAX_FILES:
        return "upload.too_many_files"
    return None


def validate_file_extension(name: str) -> bool:
    """Return True if ``name`` has a supported extension."""
    return Path(name).suffix.lower() in ALLOWED_EXTENSIONS


def parse_file(name: str, data: bytes) -> pd.DataFrame:
    """Parse raw ``data`` bytes from a CSV or XLSX file into a DataFrame.

    Raises
    ------
    ValueError
        If the file extension is not in ALLOWED_EXTENSIONS.
    Any pandas parse error is propagated to the caller.
    """
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(io.BytesIO(data))
    if suffix == ".xlsx":
        return pd.read_excel(io.BytesIO(data), engine="openpyxl")
    raise ValueError(f"Unsupported file extension: {suffix!r}")

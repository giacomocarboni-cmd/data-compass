"""
Schema inference and ERD data structures — Phase 7, Step 7.2.

Public API
----------
ColumnSchema    dataclass — one column's inferred type metadata
TableSchema     dataclass — all columns for a single table
Relationship    dataclass — a declared FK link between two tables
ERDDeclaration  dataclass — the full user-declared schema (PKs + relationships)
table_name_from_filename(name) -> str
    Derive a safe DuckDB table name from a filename.
infer_schema(table_name, df) -> TableSchema
    Infer column types from a DataFrame using pandas dtype heuristics.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ColumnSchema:
    """Metadata for a single column."""
    name: str
    inferred_type: str   # 'integer' | 'float' | 'string' | 'date' | 'boolean'
    nullable: bool
    unique_ratio: float  # distinct / total rows; 1.0 for a true PK


@dataclass
class TableSchema:
    """Schema for a single uploaded table."""
    name: str            # safe DuckDB identifier derived from the filename
    columns: list[ColumnSchema]


@dataclass
class Relationship:
    """A declared FK link from one column to another."""
    from_table: str
    from_col: str
    to_table: str
    to_col: str


@dataclass
class ERDDeclaration:
    """The full user-declared schema: table schemas, PKs, and FK relationships."""
    tables: list[TableSchema]
    primary_keys: dict[str, str] = field(default_factory=dict)   # table -> col
    relationships: list[Relationship] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def table_name_from_filename(name: str) -> str:
    """Derive a safe, lowercase DuckDB table identifier from a filename.

    The stem of the filename is lower-cased; any character that is not
    a letter, digit, or underscore is replaced by an underscore.

    Examples
    --------
    "Orders 2024.csv" -> "orders_2024"
    "sales-data.xlsx" -> "sales_data"
    """
    stem = Path(name).stem.lower()
    return re.sub(r"[^a-z0-9_]", "_", stem)


def _infer_column_type(series: pd.Series) -> str:
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "date"
    return "string"


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def infer_schema(table_name: str, df: pd.DataFrame) -> TableSchema:
    """Infer a :class:`TableSchema` from a DataFrame.

    Types are derived from pandas dtypes without any API calls.
    ``unique_ratio`` is included so the UI can suggest likely PK columns
    (those with a ratio close to 1.0).
    """
    total = max(len(df), 1)
    columns: list[ColumnSchema] = []
    for col in df.columns:
        series = df[col]
        columns.append(
            ColumnSchema(
                name=col,
                inferred_type=_infer_column_type(series),
                nullable=bool(series.isna().any()),
                unique_ratio=series.nunique() / total,
            )
        )
    return TableSchema(name=table_name, columns=columns)

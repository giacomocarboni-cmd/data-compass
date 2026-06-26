"""
Deterministic ERD validation — Phase 7, Step 7.3.

validate_erd(declaration, dataframes) runs three checks against the
actual uploaded data, flagging structural problems before any AI call:

  1. pk_not_unique       — the declared PK column contains duplicate values.
  2. fk_type_mismatch    — the FK column's inferred type differs from the
                           PK column's inferred type in the target table.
  3. fk_high_orphan_rate — more than ORPHAN_RATE_THRESHOLD (30 %) of FK
                           rows have no matching value in the PK column.

Returns an ERDValidationResult whose .issues list contains one entry per
problem found.  An empty list means the declaration is structurally clean.
Zero API calls are made.

Public API
----------
ORPHAN_RATE_THRESHOLD   float (default 0.3)
ValidationIssue         dataclass — kind, table, column, detail
ERDValidationResult     dataclass — declaration, issues + is_valid property
validate_erd(declaration, dataframes) -> ERDValidationResult
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from data_compass.erd.infer import ERDDeclaration, TableSchema

ORPHAN_RATE_THRESHOLD: float = 0.3


@dataclass
class ValidationIssue:
    """A single structural problem found during ERD validation."""
    kind: str     # 'pk_not_unique' | 'fk_type_mismatch' | 'fk_high_orphan_rate'
    table: str
    column: str
    detail: str   # human-readable explanation for the sign-off UI


@dataclass
class ERDValidationResult:
    """Result of a full deterministic ERD validation pass."""
    declaration: ERDDeclaration
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when no structural issues were found."""
        return len(self.issues) == 0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate_erd(
    declaration: ERDDeclaration,
    dataframes: dict[str, pd.DataFrame],
) -> ERDValidationResult:
    """Run all deterministic validation checks.  No API calls.

    Parameters
    ----------
    declaration:
        The user-confirmed ERDDeclaration from step 7.2.
    dataframes:
        A mapping of table_name → DataFrame matching the declared tables.
        Tables not present in this dict are skipped silently.
    """
    result = ERDValidationResult(declaration=declaration)

    table_schemas: dict[str, TableSchema] = {t.name: t for t in declaration.tables}

    _check_pk_uniqueness(result, declaration, dataframes)
    _check_fk_types(result, declaration, table_schemas)
    _check_fk_orphan_rates(result, declaration, dataframes)

    return result


# ---------------------------------------------------------------------------
# Check 1 — PK uniqueness
# ---------------------------------------------------------------------------

def _check_pk_uniqueness(
    result: ERDValidationResult,
    declaration: ERDDeclaration,
    dataframes: dict[str, pd.DataFrame],
) -> None:
    for table_name, pk_col in declaration.primary_keys.items():
        df = dataframes.get(table_name)
        if df is None or pk_col not in df.columns:
            continue
        dup_count = int(df[pk_col].duplicated(keep=False).sum())
        if dup_count > 0:
            result.issues.append(
                ValidationIssue(
                    kind="pk_not_unique",
                    table=table_name,
                    column=pk_col,
                    detail=(
                        f"Column '{pk_col}' in '{table_name}' has {dup_count} duplicate "
                        f"value(s) and cannot serve as a primary key."
                    ),
                )
            )


# ---------------------------------------------------------------------------
# Check 2 — FK ↔ PK type compatibility
# ---------------------------------------------------------------------------

def _check_fk_types(
    result: ERDValidationResult,
    declaration: ERDDeclaration,
    table_schemas: dict[str, TableSchema],
) -> None:
    for rel in declaration.relationships:
        from_schema = table_schemas.get(rel.from_table)
        to_schema = table_schemas.get(rel.to_table)
        if from_schema is None or to_schema is None:
            continue

        from_col_schema = next(
            (c for c in from_schema.columns if c.name == rel.from_col), None
        )
        to_col_schema = next(
            (c for c in to_schema.columns if c.name == rel.to_col), None
        )
        if from_col_schema is None or to_col_schema is None:
            continue

        if from_col_schema.inferred_type != to_col_schema.inferred_type:
            result.issues.append(
                ValidationIssue(
                    kind="fk_type_mismatch",
                    table=rel.from_table,
                    column=rel.from_col,
                    detail=(
                        f"FK '{rel.from_table}.{rel.from_col}' is inferred as "
                        f"'{from_col_schema.inferred_type}', but the target "
                        f"'{rel.to_table}.{rel.to_col}' is "
                        f"'{to_col_schema.inferred_type}'. A JOIN on mismatched "
                        f"types may produce no results."
                    ),
                )
            )


# ---------------------------------------------------------------------------
# Check 3 — FK orphan rate
# ---------------------------------------------------------------------------

def _check_fk_orphan_rates(
    result: ERDValidationResult,
    declaration: ERDDeclaration,
    dataframes: dict[str, pd.DataFrame],
) -> None:
    for rel in declaration.relationships:
        from_df = dataframes.get(rel.from_table)
        to_df = dataframes.get(rel.to_table)
        if from_df is None or to_df is None:
            continue
        if rel.from_col not in from_df.columns or rel.to_col not in to_df.columns:
            continue

        fk_series = from_df[rel.from_col].dropna()
        if fk_series.empty:
            continue

        pk_values = set(to_df[rel.to_col].dropna())
        orphaned = fk_series[~fk_series.isin(pk_values)]
        orphan_rate = len(orphaned) / len(fk_series)

        if orphan_rate > ORPHAN_RATE_THRESHOLD:
            pct = round(orphan_rate * 100, 1)
            result.issues.append(
                ValidationIssue(
                    kind="fk_high_orphan_rate",
                    table=rel.from_table,
                    column=rel.from_col,
                    detail=(
                        f"{pct}% of values in '{rel.from_table}.{rel.from_col}' "
                        f"have no match in '{rel.to_table}.{rel.to_col}'. A JOIN "
                        f"on this relationship will drop many rows."
                    ),
                )
            )

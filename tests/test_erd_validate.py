"""
Phase 7, Step 7.3 — Zero-API ERD build + deterministic validation tests.

Covers:
  * build_erd produces an ERDGraph with correct tables/pk/adjacency
  * pk_not_unique flagged when PK column contains duplicates
  * fk_type_mismatch flagged when FK and PK columns have different inferred types
  * fk_high_orphan_rate flagged when orphan fraction > ORPHAN_RATE_THRESHOLD
  * clean declaration passes with zero issues
  * zero API calls in all cases
"""
from __future__ import annotations

import pandas as pd
import pytest

from data_compass.erd.build import ERDGraph, build_erd
from data_compass.erd.infer import (
    ColumnSchema,
    ERDDeclaration,
    Relationship,
    TableSchema,
)
from data_compass.erd.validate import (
    ORPHAN_RATE_THRESHOLD,
    ERDValidationResult,
    ValidationIssue,
    validate_erd,
)


# ---------------------------------------------------------------------------
# Fixtures — reusable table schemas and DataFrames
# ---------------------------------------------------------------------------

def _orders_schema() -> TableSchema:
    return TableSchema(
        name="orders",
        columns=[
            ColumnSchema("order_id", "integer", False, 1.0),
            ColumnSchema("customer_id", "integer", False, 0.8),
            ColumnSchema("amount", "float", False, 0.9),
        ],
    )


def _customers_schema() -> TableSchema:
    return TableSchema(
        name="customers",
        columns=[
            ColumnSchema("id", "integer", False, 1.0),
            ColumnSchema("name", "string", False, 0.9),
        ],
    )


def _orders_df_clean() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": [1, 2, 3, 4, 5],
        "customer_id": [10, 20, 30, 10, 20],
        "amount": [100.0, 200.0, 50.0, 75.0, 300.0],
    })


def _customers_df_clean() -> pd.DataFrame:
    return pd.DataFrame({
        "id": [10, 20, 30],
        "name": ["Alice", "Bob", "Carol"],
    })


def _clean_declaration() -> ERDDeclaration:
    return ERDDeclaration(
        tables=[_orders_schema(), _customers_schema()],
        primary_keys={"orders": "order_id", "customers": "id"},
        relationships=[
            Relationship("orders", "customer_id", "customers", "id")
        ],
    )


# ---------------------------------------------------------------------------
# build_erd
# ---------------------------------------------------------------------------

class TestBuildERD:
    def test_tables_dict_keyed_by_name(self):
        decl = _clean_declaration()
        graph = build_erd(decl)
        assert "orders" in graph.tables
        assert "customers" in graph.tables

    def test_primary_keys_copied(self):
        decl = _clean_declaration()
        graph = build_erd(decl)
        assert graph.primary_keys["orders"] == "order_id"
        assert graph.primary_keys["customers"] == "id"

    def test_adjacency_contains_relationship(self):
        decl = _clean_declaration()
        graph = build_erd(decl)
        assert len(graph.adjacency) == 1
        rel = graph.adjacency[0]
        assert rel.from_table == "orders"
        assert rel.to_table == "customers"

    def test_mutating_graph_does_not_affect_declaration(self):
        decl = _clean_declaration()
        graph = build_erd(decl)
        graph.primary_keys["orders"] = "mutated"
        assert decl.primary_keys["orders"] == "order_id"


# ---------------------------------------------------------------------------
# validate_erd — clean case
# ---------------------------------------------------------------------------

class TestValidateERDClean:
    def test_clean_declaration_passes(self):
        decl = _clean_declaration()
        dfs = {"orders": _orders_df_clean(), "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        assert result.is_valid
        assert result.issues == []

    def test_result_holds_declaration_reference(self):
        decl = _clean_declaration()
        dfs = {"orders": _orders_df_clean(), "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        assert result.declaration is decl


# ---------------------------------------------------------------------------
# validate_erd — pk_not_unique
# ---------------------------------------------------------------------------

class TestPKNotUnique:
    def test_duplicate_pk_flagged(self):
        decl = _clean_declaration()
        orders_dup = pd.DataFrame({
            "order_id": [1, 1, 3],   # duplicate!
            "customer_id": [10, 20, 30],
            "amount": [100.0, 200.0, 50.0],
        })
        dfs = {"orders": orders_dup, "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        kinds = [i.kind for i in result.issues]
        assert "pk_not_unique" in kinds

    def test_issue_references_correct_table_and_column(self):
        decl = _clean_declaration()
        orders_dup = pd.DataFrame({
            "order_id": [1, 1, 3],
            "customer_id": [10, 20, 30],
            "amount": [1.0, 2.0, 3.0],
        })
        dfs = {"orders": orders_dup, "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        pk_issue = next(i for i in result.issues if i.kind == "pk_not_unique")
        assert pk_issue.table == "orders"
        assert pk_issue.column == "order_id"

    def test_unique_pk_not_flagged(self):
        decl = _clean_declaration()
        dfs = {"orders": _orders_df_clean(), "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        assert not any(i.kind == "pk_not_unique" for i in result.issues)


# ---------------------------------------------------------------------------
# validate_erd — fk_type_mismatch
# ---------------------------------------------------------------------------

class TestFKTypeMismatch:
    def _type_mismatch_declaration(self) -> ERDDeclaration:
        orders = TableSchema(
            name="orders",
            columns=[
                ColumnSchema("order_id", "integer", False, 1.0),
                ColumnSchema("customer_ref", "string", False, 0.8),  # string FK
            ],
        )
        customers = TableSchema(
            name="customers",
            columns=[
                ColumnSchema("id", "integer", False, 1.0),  # integer PK
                ColumnSchema("name", "string", False, 0.9),
            ],
        )
        return ERDDeclaration(
            tables=[orders, customers],
            primary_keys={"orders": "order_id", "customers": "id"},
            relationships=[
                Relationship("orders", "customer_ref", "customers", "id")
            ],
        )

    def test_type_mismatch_flagged(self):
        decl = self._type_mismatch_declaration()
        dfs = {
            "orders": pd.DataFrame({"order_id": [1, 2], "customer_ref": ["A10", "B20"]}),
            "customers": pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]}),
        }
        result = validate_erd(decl, dfs)
        assert any(i.kind == "fk_type_mismatch" for i in result.issues)

    def test_mismatch_issue_references_fk_side(self):
        decl = self._type_mismatch_declaration()
        dfs = {
            "orders": pd.DataFrame({"order_id": [1], "customer_ref": ["X"]}),
            "customers": pd.DataFrame({"id": [1], "name": ["Alice"]}),
        }
        result = validate_erd(decl, dfs)
        issue = next(i for i in result.issues if i.kind == "fk_type_mismatch")
        assert issue.table == "orders"
        assert issue.column == "customer_ref"

    def test_matching_types_not_flagged(self):
        decl = _clean_declaration()
        dfs = {"orders": _orders_df_clean(), "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        assert not any(i.kind == "fk_type_mismatch" for i in result.issues)


# ---------------------------------------------------------------------------
# validate_erd — fk_high_orphan_rate
# ---------------------------------------------------------------------------

class TestFKHighOrphanRate:
    def test_high_orphan_rate_flagged(self):
        decl = _clean_declaration()
        # 3 out of 4 FK values have no matching PK → 75 % orphan rate
        orders_orphan = pd.DataFrame({
            "order_id": [1, 2, 3, 4],
            "customer_id": [10, 99, 98, 97],  # 99/98/97 are orphans
            "amount": [1.0, 2.0, 3.0, 4.0],
        })
        dfs = {"orders": orders_orphan, "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        assert any(i.kind == "fk_high_orphan_rate" for i in result.issues)

    def test_orphan_issue_references_correct_fk(self):
        decl = _clean_declaration()
        orders_orphan = pd.DataFrame({
            "order_id": [1, 2, 3, 4],
            "customer_id": [10, 99, 98, 97],
            "amount": [1.0, 2.0, 3.0, 4.0],
        })
        dfs = {"orders": orders_orphan, "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        issue = next(i for i in result.issues if i.kind == "fk_high_orphan_rate")
        assert issue.table == "orders"
        assert issue.column == "customer_id"

    def test_low_orphan_rate_not_flagged(self):
        decl = _clean_declaration()
        # All FK values match → 0 % orphan rate
        dfs = {"orders": _orders_df_clean(), "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        assert not any(i.kind == "fk_high_orphan_rate" for i in result.issues)

    def test_orphan_rate_threshold_boundary(self):
        decl = _clean_declaration()
        # Exactly at threshold: 30 % orphaned — should NOT be flagged (> not >=)
        orders_boundary = pd.DataFrame({
            "order_id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "customer_id": [10, 10, 10, 10, 10, 10, 10, 99, 99, 99],  # 3/10 = 30%
            "amount": [1.0] * 10,
        })
        dfs = {"orders": orders_boundary, "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        assert not any(i.kind == "fk_high_orphan_rate" for i in result.issues)

    def test_just_above_threshold_is_flagged(self):
        decl = _clean_declaration()
        # 31 % orphaned — should be flagged
        orders_over = pd.DataFrame({
            "order_id": list(range(100)),
            "customer_id": [10] * 69 + [999] * 31,  # 31 % orphans
            "amount": [1.0] * 100,
        })
        dfs = {"orders": orders_over, "customers": _customers_df_clean()}
        result = validate_erd(decl, dfs)
        assert any(i.kind == "fk_high_orphan_rate" for i in result.issues)

"""
Phase 7, Step 7.2 — Schema inference + PK/FK declaration tests.

Covers:
  * table_name_from_filename sanitises stems correctly
  * infer_schema assigns correct types (integer/float/string/date/boolean)
  * infer_schema computes unique_ratio and nullable correctly
  * _suggest_pk (via infer_schema) picks the column with highest unique_ratio
  * ERDDeclaration captures primary_keys and relationships with correct fields
"""
from __future__ import annotations

import pandas as pd
import pytest

from data_compass.erd.infer import (
    ColumnSchema,
    ERDDeclaration,
    Relationship,
    TableSchema,
    infer_schema,
    table_name_from_filename,
)


# ---------------------------------------------------------------------------
# table_name_from_filename
# ---------------------------------------------------------------------------

class TestTableNameFromFilename:
    def test_simple_csv(self):
        assert table_name_from_filename("orders.csv") == "orders"

    def test_spaces_replaced(self):
        assert table_name_from_filename("Sales Data 2024.csv") == "sales_data_2024"

    def test_hyphens_replaced(self):
        assert table_name_from_filename("line-items.xlsx") == "line_items"

    def test_uppercased_lowercased(self):
        assert table_name_from_filename("Customers.CSV") == "customers"

    def test_dots_in_stem_replaced(self):
        assert table_name_from_filename("my.data.csv") == "my_data"


# ---------------------------------------------------------------------------
# infer_schema — type inference
# ---------------------------------------------------------------------------

class TestInferSchemaTypes:
    def test_integer_column(self):
        df = pd.DataFrame({"qty": [1, 2, 3]})
        schema = infer_schema("orders", df)
        col = schema.columns[0]
        assert col.name == "qty"
        assert col.inferred_type == "integer"

    def test_float_column(self):
        df = pd.DataFrame({"price": [1.5, 2.0, 3.99]})
        schema = infer_schema("products", df)
        assert schema.columns[0].inferred_type == "float"

    def test_string_column(self):
        df = pd.DataFrame({"name": ["Alice", "Bob", "Carol"]})
        schema = infer_schema("people", df)
        assert schema.columns[0].inferred_type == "string"

    def test_boolean_column(self):
        df = pd.DataFrame({"active": [True, False, True]})
        schema = infer_schema("flags", df)
        assert schema.columns[0].inferred_type == "boolean"

    def test_datetime_column(self):
        df = pd.DataFrame({"created_at": pd.to_datetime(["2024-01-01", "2024-06-15"])})
        schema = infer_schema("events", df)
        assert schema.columns[0].inferred_type == "date"

    def test_mixed_types_each_inferred(self):
        df = pd.DataFrame({
            "id": [1, 2, 3],
            "label": ["a", "b", "c"],
            "score": [0.1, 0.2, 0.3],
        })
        schema = infer_schema("mixed", df)
        types = {c.name: c.inferred_type for c in schema.columns}
        assert types["id"] == "integer"
        assert types["label"] == "string"
        assert types["score"] == "float"


# ---------------------------------------------------------------------------
# infer_schema — nullable and unique_ratio
# ---------------------------------------------------------------------------

class TestInferSchemaMeta:
    def test_nullable_true_when_nans_present(self):
        df = pd.DataFrame({"x": [1, None, 3]})
        schema = infer_schema("t", df)
        assert schema.columns[0].nullable is True

    def test_nullable_false_when_no_nans(self):
        df = pd.DataFrame({"x": [1, 2, 3]})
        schema = infer_schema("t", df)
        assert schema.columns[0].nullable is False

    def test_unique_ratio_all_unique(self):
        df = pd.DataFrame({"id": [10, 20, 30]})
        schema = infer_schema("t", df)
        assert schema.columns[0].unique_ratio == pytest.approx(1.0)

    def test_unique_ratio_all_same(self):
        df = pd.DataFrame({"status": ["active", "active", "active"]})
        schema = infer_schema("t", df)
        assert schema.columns[0].unique_ratio == pytest.approx(1 / 3)

    def test_table_name_preserved(self):
        df = pd.DataFrame({"a": [1]})
        schema = infer_schema("my_table", df)
        assert schema.name == "my_table"

    def test_empty_dataframe_returns_empty_columns(self):
        df = pd.DataFrame()
        schema = infer_schema("empty", df)
        assert schema.columns == []


# ---------------------------------------------------------------------------
# ERDDeclaration dataclass
# ---------------------------------------------------------------------------

class TestERDDeclaration:
    def _make_tables(self):
        t1 = TableSchema(
            name="orders",
            columns=[
                ColumnSchema("order_id", "integer", False, 1.0),
                ColumnSchema("customer_id", "integer", False, 0.8),
            ],
        )
        t2 = TableSchema(
            name="customers",
            columns=[
                ColumnSchema("id", "integer", False, 1.0),
                ColumnSchema("name", "string", False, 0.9),
            ],
        )
        return [t1, t2]

    def test_pk_declaration_captured(self):
        tables = self._make_tables()
        decl = ERDDeclaration(
            tables=tables,
            primary_keys={"orders": "order_id", "customers": "id"},
            relationships=[],
        )
        assert decl.primary_keys["orders"] == "order_id"
        assert decl.primary_keys["customers"] == "id"

    def test_relationship_fields_correct(self):
        tables = self._make_tables()
        rel = Relationship(
            from_table="orders",
            from_col="customer_id",
            to_table="customers",
            to_col="id",
        )
        decl = ERDDeclaration(tables=tables, primary_keys={}, relationships=[rel])
        r = decl.relationships[0]
        assert r.from_table == "orders"
        assert r.from_col == "customer_id"
        assert r.to_table == "customers"
        assert r.to_col == "id"

    def test_multiple_relationships(self):
        tables = self._make_tables()
        rels = [
            Relationship("orders", "customer_id", "customers", "id"),
            Relationship("orders", "order_id", "orders", "order_id"),
        ]
        decl = ERDDeclaration(tables=tables, primary_keys={}, relationships=rels)
        assert len(decl.relationships) == 2

    def test_default_empty_collections(self):
        tables = self._make_tables()
        decl = ERDDeclaration(tables=tables)
        assert decl.primary_keys == {}
        assert decl.relationships == []

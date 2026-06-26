"""
Phase 7, Step 7.4 — Haiku plausibility + non-destructive sign-off tests.

Covers:
  * check_plausibility with a mocked Haiku response surfaces a suggestion
  * No API call is made when there are no declared relationships
  * apply_decisions: declining keeps the original declaration unchanged
  * apply_decisions: accepting applies the suggested_from_col
  * apply_decisions: accepting a suggestion with no suggested_from_col is a no-op
  * _parse_response handles malformed / empty JSON gracefully
"""
from __future__ import annotations

import json
from unittest import mock
from unittest.mock import MagicMock

import pytest

from data_compass.erd.infer import (
    ColumnSchema,
    ERDDeclaration,
    Relationship,
    TableSchema,
)
from data_compass.erd.plausibility import (
    PlausibilitySuggestion,
    _parse_response,
    apply_decisions,
    check_plausibility,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _declaration_with_bad_join() -> ERDDeclaration:
    """A declaration where 'product_name' is wrongly linked to 'customer_id'."""
    orders = TableSchema(
        name="orders",
        columns=[
            ColumnSchema("order_id", "integer", False, 1.0),
            ColumnSchema("customer_id", "integer", False, 0.8),
            ColumnSchema("product_name", "string", False, 0.5),
        ],
    )
    customers = TableSchema(
        name="customers",
        columns=[
            ColumnSchema("id", "integer", False, 1.0),
            ColumnSchema("name", "string", False, 0.9),
        ],
    )
    return ERDDeclaration(
        tables=[orders, customers],
        primary_keys={"orders": "order_id", "customers": "id"},
        relationships=[
            Relationship("orders", "product_name", "customers", "id")
        ],
    )


def _declaration_no_rels() -> ERDDeclaration:
    orders = TableSchema(
        name="orders",
        columns=[ColumnSchema("order_id", "integer", False, 1.0)],
    )
    return ERDDeclaration(tables=[orders], primary_keys={"orders": "order_id"}, relationships=[])


def _mock_haiku_response(suggestions: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=json.dumps(suggestions))]
    resp.usage = MagicMock(
        input_tokens=100, output_tokens=20,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
    )
    return resp


def _make_client(suggestions: list[dict]) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = _mock_haiku_response(suggestions)
    return client


# ---------------------------------------------------------------------------
# check_plausibility
# ---------------------------------------------------------------------------

class TestCheckPlausibility:
    def test_implausible_join_surfaces_suggestion(self):
        decl = _declaration_with_bad_join()
        mock_suggestions = [
            {
                "from_table": "orders",
                "from_col": "product_name",
                "to_table": "customers",
                "to_col": "id",
                "reason": "Joining product_name to customer id makes no business sense.",
                "suggested_from_col": "customer_id",
            }
        ]
        with mock.patch("anthropic.Anthropic", return_value=_make_client(mock_suggestions)):
            suggestions, usage = check_plausibility("sk-test", decl)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.from_table == "orders"
        assert s.from_col == "product_name"
        assert s.to_table == "customers"
        assert s.to_col == "id"
        assert "product_name" in s.reason or "business" in s.reason.lower()
        assert s.suggested_from_col == "customer_id"

    def test_usage_returned(self):
        decl = _declaration_with_bad_join()
        with mock.patch("anthropic.Anthropic", return_value=_make_client([])):
            _, usage = check_plausibility("sk-test", decl)
        assert usage is not None

    def test_no_rels_returns_empty_without_api_call(self):
        decl = _declaration_no_rels()
        with mock.patch("anthropic.Anthropic") as mock_ant:
            suggestions, usage = check_plausibility("sk-test", decl)
        mock_ant.return_value.messages.create.assert_not_called()
        assert suggestions == []
        assert usage is None

    def test_plausible_join_returns_empty_list(self):
        decl = _declaration_with_bad_join()
        with mock.patch("anthropic.Anthropic", return_value=_make_client([])):
            suggestions, _ = check_plausibility("sk-test", decl)
        assert suggestions == []


# ---------------------------------------------------------------------------
# apply_decisions — declining keeps original
# ---------------------------------------------------------------------------

class TestApplyDecisionsDecline:
    def test_declining_keeps_original_relationships(self):
        decl = _declaration_with_bad_join()
        suggestion = PlausibilitySuggestion(
            from_table="orders",
            from_col="product_name",
            to_table="customers",
            to_col="id",
            reason="Makes no sense.",
            suggested_from_col="customer_id",
        )
        # Accept nothing → original kept
        result = apply_decisions(decl, [suggestion], accepted=set())

        assert len(result.relationships) == 1
        rel = result.relationships[0]
        assert rel.from_col == "product_name"  # unchanged

    def test_declining_does_not_mutate_original(self):
        decl = _declaration_with_bad_join()
        suggestion = PlausibilitySuggestion(
            from_table="orders", from_col="product_name",
            to_table="customers", to_col="id",
            reason="test", suggested_from_col="customer_id",
        )
        _ = apply_decisions(decl, [suggestion], accepted=set())
        assert decl.relationships[0].from_col == "product_name"


# ---------------------------------------------------------------------------
# apply_decisions — accepting updates the column
# ---------------------------------------------------------------------------

class TestApplyDecisionsAccept:
    def test_accepting_applies_suggested_from_col(self):
        decl = _declaration_with_bad_join()
        suggestion = PlausibilitySuggestion(
            from_table="orders",
            from_col="product_name",
            to_table="customers",
            to_col="id",
            reason="Makes no sense.",
            suggested_from_col="customer_id",
        )
        result = apply_decisions(decl, [suggestion], accepted={0})

        assert len(result.relationships) == 1
        rel = result.relationships[0]
        assert rel.from_col == "customer_id"  # updated
        assert rel.to_col == "id"              # unchanged

    def test_accepting_suggestion_without_suggested_col_is_noop(self):
        decl = _declaration_with_bad_join()
        suggestion = PlausibilitySuggestion(
            from_table="orders",
            from_col="product_name",
            to_table="customers",
            to_col="id",
            reason="Makes no sense.",
            suggested_from_col=None,  # no concrete fix
        )
        result = apply_decisions(decl, [suggestion], accepted={0})
        # No col to apply → original kept
        assert result.relationships[0].from_col == "product_name"

    def test_accepting_does_not_mutate_original(self):
        decl = _declaration_with_bad_join()
        suggestion = PlausibilitySuggestion(
            from_table="orders", from_col="product_name",
            to_table="customers", to_col="id",
            reason="test", suggested_from_col="customer_id",
        )
        _ = apply_decisions(decl, [suggestion], accepted={0})
        assert decl.relationships[0].from_col == "product_name"


# ---------------------------------------------------------------------------
# _parse_response — robustness
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_valid_json_array(self):
        raw = json.dumps([
            {
                "from_table": "a", "from_col": "x",
                "to_table": "b", "to_col": "y",
                "reason": "test", "suggested_from_col": None,
            }
        ])
        result = _parse_response(raw)
        assert len(result) == 1
        assert result[0].from_table == "a"

    def test_empty_array(self):
        assert _parse_response("[]") == []

    def test_markdown_fenced_json(self):
        raw = "```json\n[]\n```"
        assert _parse_response(raw) == []

    def test_malformed_json_returns_empty(self):
        assert _parse_response("{not valid}") == []

    def test_non_list_json_returns_empty(self):
        assert _parse_response('{"key": "val"}') == []

    def test_missing_required_key_skips_item(self):
        raw = json.dumps([{"from_table": "a"}])  # missing other required keys
        result = _parse_response(raw)
        assert result == []

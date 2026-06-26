"""Unit tests for Step 3.2 — Anthropic client wrapper + SQL prompt."""
from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock, patch

from data_compass.llm.sql_prompt import (
    SYSTEM_INSTRUCTIONS,
    build_schema_text,
    extract_sql,
)
from data_compass.data.loader import ColumnInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIMPLE_SCHEMA: dict = {
    "transactions": [
        ColumnInfo("transaction_uid", "VARCHAR", False),
        ColumnInfo("property_id",     "VARCHAR", False),
        ColumnInfo("price",            "INTEGER", False),
        ColumnInfo("transfer_date",   "DATE",    False),
    ],
    "properties": [
        ColumnInfo("property_id",   "VARCHAR", False),
        ColumnInfo("county",        "VARCHAR", True),
        ColumnInfo("property_type", "VARCHAR", True),
    ],
}

_REGISTRY_ENTRY: dict = {
    "name": "UK Property Sales 2024",
    "schema_hints": {
        "primary_keys": {"transactions": "transaction_uid", "properties": "property_id"},
        "foreign_keys": [
            {"from_table": "transactions", "from_column": "property_id",
             "to_table": "properties", "to_column": "property_id"}
        ],
    },
}


# ---------------------------------------------------------------------------
# SYSTEM_INSTRUCTIONS
# ---------------------------------------------------------------------------

class TestSystemInstructions:
    def test_instructions_non_empty(self):
        assert SYSTEM_INSTRUCTIONS.strip()

    def test_instructions_mention_select_only(self):
        assert "SELECT" in SYSTEM_INSTRUCTIONS

    def test_instructions_mention_sql_fence(self):
        assert "```sql" in SYSTEM_INSTRUCTIONS


# ---------------------------------------------------------------------------
# build_schema_text
# ---------------------------------------------------------------------------

class TestBuildSchemaText:
    def test_includes_dataset_name(self):
        text = build_schema_text(_SIMPLE_SCHEMA, _REGISTRY_ENTRY)
        assert "UK Property Sales 2024" in text

    def test_includes_table_names(self):
        text = build_schema_text(_SIMPLE_SCHEMA, _REGISTRY_ENTRY)
        assert "transactions" in text
        assert "properties" in text

    def test_includes_column_names(self):
        text = build_schema_text(_SIMPLE_SCHEMA, _REGISTRY_ENTRY)
        assert "price" in text
        assert "county" in text

    def test_includes_pk_hints(self):
        text = build_schema_text(_SIMPLE_SCHEMA, _REGISTRY_ENTRY)
        assert "transaction_uid" in text
        assert "property_id" in text

    def test_includes_fk_relationship(self):
        text = build_schema_text(_SIMPLE_SCHEMA, _REGISTRY_ENTRY)
        assert "transactions" in text and "properties" in text
        assert "→" in text or "->" in text


# ---------------------------------------------------------------------------
# extract_sql
# ---------------------------------------------------------------------------

class TestExtractSql:
    def test_extracts_from_sql_fence(self):
        response = "```sql\nSELECT * FROM transactions\n```"
        assert extract_sql(response) == "SELECT * FROM transactions"

    def test_extracts_from_plain_fence(self):
        response = "```\nSELECT 1\n```"
        assert extract_sql(response) == "SELECT 1"

    def test_strips_whitespace(self):
        response = "```sql\n  SELECT 1  \n```"
        assert extract_sql(response) == "SELECT 1"

    def test_fallback_returns_full_text(self):
        raw = "SELECT * FROM transactions"
        assert extract_sql(raw) == raw

    def test_multiline_sql_preserved(self):
        sql = "SELECT county,\n  AVG(price)\nFROM transactions\nGROUP BY county"
        response = f"```sql\n{sql}\n```"
        assert extract_sql(response) == sql


# ---------------------------------------------------------------------------
# generate_sql (mocked API)
# ---------------------------------------------------------------------------

class TestGenerateSql:
    def _make_mock_response(self, sql_text: str):
        """Build a minimal mock Anthropic response object."""
        response = MagicMock()
        response.content = [MagicMock(text=f"```sql\n{sql_text}\n```")]
        response.usage = MagicMock(
            input_tokens=120,
            output_tokens=30,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        return response

    def test_returns_extracted_sql(self):
        expected_sql = "SELECT county, COUNT(*) FROM transactions GROUP BY county"
        with patch("data_compass.llm.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = (
                self._make_mock_response(expected_sql)
            )
            from data_compass.llm.client import generate_sql
            sql, usage = generate_sql("sk-ant-test", "schema text", "How many by county?")

        assert sql == expected_sql

    def test_returns_usage_object(self):
        with patch("data_compass.llm.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = (
                self._make_mock_response("SELECT 1")
            )
            from data_compass.llm.client import generate_sql
            _, usage = generate_sql("sk-ant-test", "schema", "question")

        assert hasattr(usage, "input_tokens")
        assert hasattr(usage, "output_tokens")

    def test_prompt_includes_cache_control(self):
        with patch("data_compass.llm.client.anthropic.Anthropic") as MockClient:
            mock_create = MockClient.return_value.messages.create
            mock_create.return_value = self._make_mock_response("SELECT 1")

            from data_compass.llm.client import generate_sql
            generate_sql("sk-ant-test", "schema text", "question")

            call_kwargs = mock_create.call_args.kwargs
            system_blocks = call_kwargs["system"]

        assert isinstance(system_blocks, list)
        assert len(system_blocks) >= 2
        for block in system_blocks:
            assert "cache_control" in block, "Every system block must carry cache_control"
            assert block["cache_control"] == {"type": "ephemeral"}

    def test_prompt_includes_schema_text(self):
        schema_text = "Dataset: UK Property Sales\nTable: transactions\n  price INTEGER"
        with patch("data_compass.llm.client.anthropic.Anthropic") as MockClient:
            mock_create = MockClient.return_value.messages.create
            mock_create.return_value = self._make_mock_response("SELECT 1")

            from data_compass.llm.client import generate_sql
            generate_sql("sk-ant-test", schema_text, "question")

            system_blocks = mock_create.call_args.kwargs["system"]
            block_texts = [b["text"] for b in system_blocks]

        assert any(schema_text in t for t in block_texts)

    def test_uses_sonnet_by_default(self):
        from data_compass.config import MODEL_SONNET
        with patch("data_compass.llm.client.anthropic.Anthropic") as MockClient:
            mock_create = MockClient.return_value.messages.create
            mock_create.return_value = self._make_mock_response("SELECT 1")

            from data_compass.llm.client import generate_sql
            generate_sql("sk-ant-test", "schema", "question")

        assert mock_create.call_args.kwargs["model"] == MODEL_SONNET

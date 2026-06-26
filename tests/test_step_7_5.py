"""
Phase 7, Step 7.5 — Uploaded dataset queryable with ERD join.

User journey (AppTest, all API calls mocked):
  A logged-in recruiter has already completed the upload + ERD flow.
  Session state is pre-populated with:
    - uploaded_files: two related DataFrames (orders, customers)
    - erd_signed_off: an ERDDeclaration with orders.customer_id → customers.id
  The user navigates to the Query tab, ticks "Query your uploaded data",
  asks a cross-table question, and receives a result whose SQL performs a
  JOIN across both uploaded tables.

The Anthropic SDK is mocked; DuckDB executes the SQL for real; auth and
cache use isolated in-memory SQLite stores.
"""
from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from data_compass.auth import recruiter, store
from data_compass.cache import store as cache_store
from data_compass.config import MODEL_SONNET
from data_compass.erd.infer import (
    ColumnSchema,
    ERDDeclaration,
    Relationship,
    TableSchema,
)
from data_compass.i18n import t
from data_compass.upload.ingest import ParsedFile

_OWNER_KEY = "sk-ant-owner-upload-test"

# ---------------------------------------------------------------------------
# Uploaded data fixtures
# ---------------------------------------------------------------------------

_ORDERS_DF = pd.DataFrame({
    "order_id": [1, 2, 3],
    "customer_id": [10, 20, 10],
    "amount": [100.0, 250.0, 75.0],
})

_CUSTOMERS_DF = pd.DataFrame({
    "id": [10, 20],
    "name": ["Alice", "Bob"],
})

_PARSED_FILES = [
    ParsedFile("orders.csv", _ORDERS_DF),
    ParsedFile("customers.csv", _CUSTOMERS_DF),
]

# The JOIN SQL the mock will return for a cross-table question
_JOIN_SQL = (
    "SELECT c.name, SUM(o.amount) AS total_amount "
    "FROM orders o "
    "JOIN customers c ON o.customer_id = c.id "
    "GROUP BY c.name "
    "ORDER BY total_amount DESC"
)
_GEN_PAYLOAD = (
    '{"sql_template": "' + _JOIN_SQL + '", "param_defs": [], "params": {}}'
)
_QUESTION = "What is the total amount per customer?"

# ---------------------------------------------------------------------------
# Signed-off ERD
# ---------------------------------------------------------------------------

_ERD_SIGNED_OFF = ERDDeclaration(
    tables=[
        TableSchema(
            name="orders",
            columns=[
                ColumnSchema("order_id", "integer", False, 1.0),
                ColumnSchema("customer_id", "integer", False, 0.67),
                ColumnSchema("amount", "float", False, 1.0),
            ],
        ),
        TableSchema(
            name="customers",
            columns=[
                ColumnSchema("id", "integer", False, 1.0),
                ColumnSchema("name", "string", False, 1.0),
            ],
        ),
    ],
    primary_keys={"orders": "order_id", "customers": "id"},
    relationships=[Relationship("orders", "customer_id", "customers", "id")],
)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _usage(inp=400, out=80):
    u = MagicMock()
    u.input_tokens = inp
    u.output_tokens = out
    u.cache_creation_input_tokens = 0
    u.cache_read_input_tokens = 0
    return u


def _sdk_response(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = _usage()
    return resp


def _make_client():
    def _create(*args, model=None, **kwargs):
        if model == MODEL_SONNET:
            return _sdk_response(_GEN_PAYLOAD)
        return _sdk_response("Alice has the most spending.")

    client = MagicMock()
    client.messages.create.side_effect = _create
    return client


def _fake_embed(texts):
    return np.array([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cache_conn():
    c = cache_store.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def auth_conn():
    c = store.connect(":memory:")
    recruiter.ensure_schema(c)
    yield c
    c.close()


def _patches(auth_conn, cache_conn):
    return (
        mock.patch("data_compass.auth.resource.get_auth_conn", return_value=auth_conn),
        mock.patch("data_compass.cache.resource.get_cache_conn", return_value=cache_conn),
        mock.patch(
            "data_compass.cache.generate.embed_question",
            side_effect=lambda q, embed_fn=None: _fake_embed([q])[0],
        ),
        mock.patch("anthropic.Anthropic", return_value=_make_client()),
        mock.patch("data_compass.config.OWNER_API_KEY", _OWNER_KEY),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _input_by_label(at, label: str):
    return next(ti for ti in at.text_input if ti.label == label)


def _button_by_label(at, label: str):
    return next(b for b in at.button if b.label == label)


def _nav(at, dest: str):
    return at.radio[0].set_value(dest).run()


def _login_recruiter(at, token: str, auth_conn):
    at = _nav(at, t("app.nav.account"))
    _input_by_label(at, t("auth.recruiter_token_label")).set_value(token)
    return _button_by_label(at, t("auth.recruiter_login_button")).click().run()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUploadedDatasetQueryable:
    def test_uploaded_dataset_queried_with_erd_join(self, auth_conn, cache_conn):
        token = recruiter.create_recruiter_token(auth_conn, "TestCorp", cap=10)

        p1, p2, p3, p4, p5 = _patches(auth_conn, cache_conn)
        with p1, p2, p3, p4, p5:
            at = AppTest.from_file("app.py", default_timeout=60)

            # Pre-populate upload + ERD state (simulates completed flow)
            at.session_state["uploaded_files"] = _PARSED_FILES
            at.session_state["erd_signed_off"] = _ERD_SIGNED_OFF

            at = at.run()

            # Log in as recruiter
            at = _login_recruiter(at, token, auth_conn)
            assert at.session_state["auth_tier"] == "recruiter"

            # Navigate to Query tab
            at = _nav(at, t("app.nav.query"))

            # The "use uploaded data" checkbox should be visible
            upload_cb = next(
                (cb for cb in at.checkbox if t("query.use_uploaded_data") in cb.label),
                None,
            )
            assert upload_cb is not None, "Upload data checkbox not found in Query tab"

            # Tick the checkbox to query uploaded data
            at = upload_cb.check().run()

            # Ask the cross-table question
            at.text_area[0].set_value(_QUESTION)
            at = _button_by_label(at, t("query.submit_button")).click().run()

        assert "query_result" in at.session_state, "No query_result in session state after Ask"
        result = at.session_state["query_result"]
        assert result.error is None, f"Query errored: {result.error}"
        assert result.cache_tier == "miss"

        # The SQL must reference both uploaded tables (confirming the JOIN was used)
        sql_lower = result.sql.lower()
        assert "orders" in sql_lower
        assert "customers" in sql_lower
        assert "join" in sql_lower

        # The result DataFrame must have the expected columns
        assert "name" in result.dataframe.columns
        assert "total_amount" in result.dataframe.columns

    def test_uploaded_data_checkbox_absent_without_signed_off_erd(
        self, auth_conn, cache_conn
    ):
        """Without a signed-off ERD the toggle must not appear."""
        token = recruiter.create_recruiter_token(auth_conn, "TestCorp", cap=5)
        p1, p2, p3, p4, p5 = _patches(auth_conn, cache_conn)
        with p1, p2, p3, p4, p5:
            at = AppTest.from_file("app.py", default_timeout=60).run()
            at = _login_recruiter(at, token, auth_conn)
            at = _nav(at, t("app.nav.query"))

        upload_cb = next(
            (cb for cb in at.checkbox if t("query.use_uploaded_data") in cb.label),
            None,
        )
        assert upload_cb is None

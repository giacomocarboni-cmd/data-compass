"""
Phase 7 completion test — full upload → ERD sign-off → cross-table query.

User journey (AppTest, all API calls mocked):
  A logged-in recruiter has 2 related files already parsed into session
  state (simulating the upload step) and an ERD declaration pre-set
  (simulating the schema confirmation step).  The session is populated
  this way because st.file_uploader upload simulation is done at the
  unit level (test_upload.py); the completion test focuses on the
  integration from ERD onwards.

  Specifically:
    1. Navigate to the Upload tab → the ERD validation runs automatically
       and surfaces ≥1 deterministic issue (pk_not_unique on order_id,
       which has duplicates in the data).
    2. The user clicks "Sign off ERD" despite the issue.
    3. The user navigates to the Query tab, ticks "Query your uploaded
       data", asks a cross-table question, and gets a result whose SQL
       contains a JOIN referencing both uploaded tables.
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

_OWNER_KEY = "sk-ant-owner-p7-completion"

# ---------------------------------------------------------------------------
# Test data — orders has a duplicate PK so validation surfaces an issue
# ---------------------------------------------------------------------------

_ORDERS_DF = pd.DataFrame({
    "order_id":    [1, 1, 3],         # duplicate → pk_not_unique surfaced
    "customer_id": [10, 20, 10],
    "amount":      [100.0, 250.0, 75.0],
})

_CUSTOMERS_DF = pd.DataFrame({
    "id":   [10, 20],
    "name": ["Alice", "Bob"],
})

_PARSED_FILES = [
    ParsedFile("orders.csv",    _ORDERS_DF),
    ParsedFile("customers.csv", _CUSTOMERS_DF),
]

_ERD_DECLARATION = ERDDeclaration(
    tables=[
        TableSchema(
            name="orders",
            columns=[
                ColumnSchema("order_id",    "integer", False, 0.67),  # not unique!
                ColumnSchema("customer_id", "integer", False, 0.67),
                ColumnSchema("amount",      "float",   False, 1.0),
            ],
        ),
        TableSchema(
            name="customers",
            columns=[
                ColumnSchema("id",   "integer", False, 1.0),
                ColumnSchema("name", "string",  False, 1.0),
            ],
        ),
    ],
    primary_keys={"orders": "order_id", "customers": "id"},
    relationships=[Relationship("orders", "customer_id", "customers", "id")],
)

# The mocked Sonnet response for the cross-table question
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
# Mock helpers
# ---------------------------------------------------------------------------

def _usage(inp=400, out=80):
    u = MagicMock()
    u.input_tokens = inp
    u.output_tokens = out
    u.cache_creation_input_tokens = 0
    u.cache_read_input_tokens = 0
    return u


def _make_client():
    def _create(*args, model=None, **kwargs):
        if model == MODEL_SONNET:
            return MagicMock(
                content=[MagicMock(text=_GEN_PAYLOAD)],
                usage=_usage(),
            )
        return MagicMock(
            content=[MagicMock(text="Alice has the highest total.")],
            usage=_usage(),
        )
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
        mock.patch("data_compass.auth.resource.get_auth_conn",   return_value=auth_conn),
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


def _login_recruiter(at, token: str):
    at = _nav(at, t("app.nav.account"))
    _input_by_label(at, t("auth.recruiter_token_label")).set_value(token)
    return _button_by_label(at, t("auth.recruiter_login_button")).click().run()


# ---------------------------------------------------------------------------
# Phase 7 completion test
# ---------------------------------------------------------------------------

class TestPhase7Completion:
    def test_upload_erd_sign_off_then_cross_table_query(self, auth_conn, cache_conn):
        """Full user journey: ERD → ≥1 correction surfaced → sign-off → JOIN query."""
        token = recruiter.create_recruiter_token(auth_conn, "Acme", cap=10)

        p1, p2, p3, p4, p5 = _patches(auth_conn, cache_conn)
        with p1, p2, p3, p4, p5:
            at = AppTest.from_file("app.py", default_timeout=60)

            # Pre-populate upload state (files parsed + schema declared)
            at.session_state["uploaded_files"]  = _PARSED_FILES
            at.session_state["erd_declaration"] = _ERD_DECLARATION
            # Phase 8 adds a Terms-of-Use gate before the upload flow; accept it
            # so this Phase 7 journey reaches the ERD validation as before.
            at.session_state["tos_accepted"] = True

            at = at.run()

            # --- Step 1: log in as recruiter ---
            at = _login_recruiter(at, token)
            assert at.session_state["auth_tier"] == "recruiter"

            # --- Step 2: navigate to Upload → validation runs automatically ---
            at = _nav(at, t("app.nav.upload"))

            # Validation must have run and stored a result
            assert "erd_validation" in at.session_state
            validation = at.session_state["erd_validation"]

            # ≥1 deterministic correction must be surfaced (pk_not_unique on order_id)
            assert not validation.is_valid, "Expected ≥1 validation issue"
            issue_kinds = [i.kind for i in validation.issues]
            assert "pk_not_unique" in issue_kinds

            # The warning text must be visible in the rendered UI
            warnings_text = " ".join(w.value for w in at.warning)
            assert "order_id" in warnings_text

            # --- Step 3: sign off the ERD despite the issue ---
            sign_off_btn = next(
                b for b in at.button
                if b.label == t("erd_signoff.sign_off_button")
            )
            at = sign_off_btn.click().run()

            assert "erd_signed_off" in at.session_state

            # --- Step 4: navigate to Query, enable uploaded data toggle ---
            at = _nav(at, t("app.nav.query"))

            upload_cb = next(
                cb for cb in at.checkbox
                if cb.label == t("query.use_uploaded_data")
            )
            at = upload_cb.check().run()

            # --- Step 5: ask a cross-table question ---
            at.text_area[0].set_value(_QUESTION)
            at = _button_by_label(at, t("query.submit_button")).click().run()

        # --- Verify the result contains a cross-table JOIN ---
        assert "query_result" in at.session_state
        result = at.session_state["query_result"]

        assert result.error is None, f"Query returned error: {result.error}"
        assert result.cache_tier == "miss"

        sql_lower = result.sql.lower()
        assert "orders"    in sql_lower, "SQL does not reference 'orders'"
        assert "customers" in sql_lower, "SQL does not reference 'customers'"
        assert "join"      in sql_lower, "SQL does not contain a JOIN"

        # The result DataFrame must contain customer names and totals
        assert "name"         in result.dataframe.columns
        assert "total_amount" in result.dataframe.columns
        assert len(result.dataframe) > 0

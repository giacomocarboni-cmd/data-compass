"""
Phase 8, Step 8.3 — Ambiguous-column Haiku classification tests (mocked Haiku).

Covers:
  * find_ambiguous_columns selects text columns with a soft personal hint
    that the deterministic scan did not already flag, and excludes numeric/
    flagged/clean columns;
  * an ambiguous column is escalated to Haiku and classified as personal;
  * the sample sent is minimal (≤ SAMPLE_SIZE distinct, truncated values) —
    never the full raw column;
  * clearly-clean inputs are NOT sent (no API call);
  * columns Haiku does not mention default to not-personal.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pandas as pd

from data_compass.config import MODEL_HAIKU
from data_compass.pii import classify as classify_mod
from data_compass.pii.classify import (
    MAX_VALUE_LEN,
    SAMPLE_SIZE,
    classify_ambiguous_columns,
    find_ambiguous_columns,
)
from data_compass.pii.scan import scan_dataframe

_API_KEY = "sk-ant-test"


def _make_client(payload: str):
    """A mocked Anthropic client whose create() returns the given JSON text."""
    usage = MagicMock(input_tokens=120, output_tokens=40,
                      cache_creation_input_tokens=0, cache_read_input_tokens=0)
    resp = MagicMock()
    resp.content = [MagicMock(text=payload)]
    resp.usage = usage
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(classify_mod.anthropic, "Anthropic", lambda api_key=None: client)


# ---------------------------------------------------------------------------
# find_ambiguous_columns
# ---------------------------------------------------------------------------

class TestFindAmbiguous:
    def _df(self):
        return pd.DataFrame({
            "customer_id": [1, 2, 3],                       # numeric → no
            "customer_name": ["Alice Smith", "Bob Jones", "Alice Smith"],  # yes
            "product_name": ["Widget", "Gadget", "Sprocket"],              # yes
            "email": ["a@b.com", "c@d.com", "e@f.com"],     # flagged by scan → no
            "quantity": [10, 20, 30],                        # numeric → no
        })

    def test_selects_text_columns_with_hint(self):
        df = self._df()
        scan = scan_dataframe("t", df)
        ambiguous = find_ambiguous_columns(df, scan)
        assert set(ambiguous) == {"customer_name", "product_name"}

    def test_excludes_flagged_columns(self):
        df = self._df()
        scan = scan_dataframe("t", df)
        assert "email" not in find_ambiguous_columns(df, scan)

    def test_no_hint_no_escalation(self):
        df = pd.DataFrame({"colour": ["red", "green"], "size": [1, 2]})
        scan = scan_dataframe("t", df)
        assert find_ambiguous_columns(df, scan) == []


# ---------------------------------------------------------------------------
# classify_ambiguous_columns — escalation
# ---------------------------------------------------------------------------

class TestClassify:
    def _df(self):
        return pd.DataFrame({
            "customer_name": ["Alice Smith", "Bob Jones", "Alice Smith"],
            "product_name": ["Widget", "Gadget", "Sprocket"],
            "quantity": [10, 20, 30],
        })

    _PAYLOAD = json.dumps({
        "classifications": [
            {"column": "customer_name", "is_personal": True,
             "pii_type": "name", "reason": "Looks like people's names."},
            {"column": "product_name", "is_personal": False,
             "pii_type": None, "reason": "Generic product names."},
        ]
    })

    def test_personal_column_identified(self, monkeypatch):
        client = _make_client(self._PAYLOAD)
        _patch_client(monkeypatch, client)
        df = self._df()
        scan = scan_dataframe("t", df)
        result = classify_ambiguous_columns(_API_KEY, "t", df, scan)

        personal = {c.column for c in result.personal_columns}
        assert personal == {"customer_name"}
        product = next(c for c in result.classifications if c.column == "product_name")
        assert product.is_personal is False

    def test_haiku_called_once_with_haiku_model(self, monkeypatch):
        client = _make_client(self._PAYLOAD)
        _patch_client(monkeypatch, client)
        df = self._df()
        scan = scan_dataframe("t", df)
        classify_ambiguous_columns(_API_KEY, "t", df, scan)

        assert client.messages.create.call_count == 1
        assert client.messages.create.call_args.kwargs["model"] == MODEL_HAIKU

    def test_sample_is_minimal_and_distinct(self, monkeypatch):
        client = _make_client(self._PAYLOAD)
        _patch_client(monkeypatch, client)
        df = self._df()
        scan = scan_dataframe("t", df)
        classify_ambiguous_columns(_API_KEY, "t", df, scan)

        sent = client.messages.create.call_args.kwargs["messages"][0]["content"]
        body = sent.split("untrusted data) -----")[1].split("----- END")[0]
        samples = json.loads(body)
        # Distinct values only ("Alice Smith" appears twice → once in sample).
        assert samples["customer_name"] == ["Alice Smith", "Bob Jones"]
        # Never more than SAMPLE_SIZE values per column.
        assert all(len(v) <= SAMPLE_SIZE for v in samples.values())

    def test_long_values_truncated(self, monkeypatch):
        client = _make_client(self._PAYLOAD)
        _patch_client(monkeypatch, client)
        long_name = "X" * 200
        df = pd.DataFrame({"customer_name": [long_name, "Bob"]})
        scan = scan_dataframe("t", df)
        classify_ambiguous_columns(_API_KEY, "t", df, scan)

        sent = client.messages.create.call_args.kwargs["messages"][0]["content"]
        body = sent.split("untrusted data) -----")[1].split("----- END")[0]
        samples = json.loads(body)
        assert all(len(v) <= MAX_VALUE_LEN for v in samples["customer_name"])

    def test_unmentioned_column_defaults_not_personal(self, monkeypatch):
        # Haiku replies about only one of the two ambiguous columns.
        payload = json.dumps({"classifications": [
            {"column": "customer_name", "is_personal": True,
             "pii_type": "name", "reason": "names"},
        ]})
        client = _make_client(payload)
        _patch_client(monkeypatch, client)
        df = self._df()
        scan = scan_dataframe("t", df)
        result = classify_ambiguous_columns(_API_KEY, "t", df, scan)

        product = next(c for c in result.classifications if c.column == "product_name")
        assert product.is_personal is False


# ---------------------------------------------------------------------------
# No API call when nothing is ambiguous
# ---------------------------------------------------------------------------

class TestNoEscalation:
    def test_clean_input_makes_no_api_call(self, monkeypatch):
        client = _make_client("{}")
        _patch_client(monkeypatch, client)
        df = pd.DataFrame({
            "order_id": [1, 2, 3],
            "amount": [9.99, 14.5, 3.25],
            "email": ["a@b.com", "c@d.com", "e@f.com"],  # flagged, not ambiguous
        })
        scan = scan_dataframe("t", df)
        result = classify_ambiguous_columns(_API_KEY, "t", df, scan)

        assert result.classifications == []
        client.messages.create.assert_not_called()

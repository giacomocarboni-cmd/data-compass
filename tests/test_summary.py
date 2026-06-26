"""Tests for Step 4.2 — result summary generation (Anthropic API fully mocked)."""
from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock

import pandas as pd
import pytest

from data_compass.llm.summary import generate_summary
from data_compass.config import MODEL_HAIKU


def _make_response(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=100, output_tokens=40)
    return resp


_SAMPLE_DF = pd.DataFrame({
    "county": ["Greater London", "West Yorkshire", "Hampshire"],
    "sales": [312, 180, 142],
})

_QUESTION = "How many sales per county?"


class TestGenerateSummaryMocked:
    def test_returns_text_and_usage(self):
        with mock.patch("data_compass.llm.summary.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _make_response(
                "Greater London led sales with 312 transactions."
            )
            text, usage = generate_summary("sk-ant-test", _QUESTION, _SAMPLE_DF)

        assert isinstance(text, str)
        assert len(text) > 0
        assert usage is not None

    def test_uses_haiku_by_default(self):
        with mock.patch("data_compass.llm.summary.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _make_response("Summary.")
            generate_summary("sk-ant-test", _QUESTION, _SAMPLE_DF)
            call_kwargs = MockClient.return_value.messages.create.call_args
        assert call_kwargs.kwargs.get("model") == MODEL_HAIKU

    def test_prompt_contains_question(self):
        with mock.patch("data_compass.llm.summary.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _make_response("X")
            generate_summary("sk-ant-test", _QUESTION, _SAMPLE_DF)
            call_kwargs = MockClient.return_value.messages.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0] if call_kwargs.args else []
        content = str(call_kwargs)
        assert _QUESTION in content

    def test_prompt_contains_result_data(self):
        with mock.patch("data_compass.llm.summary.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _make_response("X")
            generate_summary("sk-ant-test", _QUESTION, _SAMPLE_DF)
            call_kwargs = MockClient.return_value.messages.create.call_args
        content = str(call_kwargs)
        assert "Greater London" in content

    def test_strips_whitespace_from_response(self):
        with mock.patch("data_compass.llm.summary.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _make_response(
                "  \n  Summary text.  \n  "
            )
            text, _ = generate_summary("sk-ant-test", _QUESTION, _SAMPLE_DF)
        assert text == "Summary text."


class TestGenerateSummaryNoCall:
    def test_empty_df_returns_none_without_api_call(self):
        with mock.patch("data_compass.llm.summary.anthropic.Anthropic") as MockClient:
            text, usage = generate_summary("sk-ant-test", _QUESTION, pd.DataFrame())
        MockClient.assert_not_called()
        assert text is None
        assert usage is None

    def test_none_df_returns_none_without_api_call(self):
        with mock.patch("data_compass.llm.summary.anthropic.Anthropic") as MockClient:
            text, usage = generate_summary("sk-ant-test", _QUESTION, None)
        MockClient.assert_not_called()
        assert text is None
        assert usage is None

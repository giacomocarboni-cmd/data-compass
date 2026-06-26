"""
Anthropic SDK wrapper for SQL generation.

All calls use prompt caching: the stable SYSTEM_INSTRUCTIONS and the
dataset schema are marked with ``cache_control`` so repeated queries
against the same dataset hit the prompt cache rather than re-sending
the full context each time.
"""
from __future__ import annotations

import anthropic

from data_compass.config import MODEL_SONNET
from data_compass.llm.sql_prompt import SYSTEM_INSTRUCTIONS, extract_sql


def generate_sql(
    api_key: str,
    schema_text: str,
    question: str,
    *,
    model: str = MODEL_SONNET,
) -> tuple[str, anthropic.types.Usage]:
    """
    Call the Anthropic Messages API to generate a SQL query.

    The system prompt is split into two cache-eligible blocks:
    - Block 1 (SYSTEM_INSTRUCTIONS): stable across all queries — cached after
      the first call.
    - Block 2 (schema_text): stable per dataset — cached after the first query
      against that dataset.

    Parameters
    ----------
    api_key:
        The user's BYOK key (or owner key for authenticated tiers).
    schema_text:
        Output of ``build_schema_text()``.
    question:
        The user's natural-language question.
    model:
        Model ID; defaults to Sonnet (the generation model).

    Returns
    -------
    (sql, usage)
        sql   — extracted SQL string (may still fail the safety guard).
        usage — ``anthropic.types.Usage`` with token counts for cost accounting.
    """
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_INSTRUCTIONS,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": schema_text,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": question}],
    )

    sql = extract_sql(response.content[0].text)
    return sql, response.usage

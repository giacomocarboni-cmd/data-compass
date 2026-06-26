"""
Tier 3 — Haiku adjudication + parameter extraction — Phase 5, Step 5.4.

Given the user's question and a short list of FAISS-retrieved candidate
templates, ask the cheap model (Haiku) to decide whether any candidate truly
answers the same question and, if so, extract the parameter values implied by
the new question. A match is only accepted when the model's confidence meets
the configured threshold.

The adjudication is the last cheap step before falling through to expensive
Sonnet generation (Tier 4).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic

from data_compass.cache.store import Template
from data_compass.config import CACHE_THRESHOLD, MODEL_HAIKU

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM = (
    "You decide whether a NEW analytics question can be answered by REUSING the "
    "exact SQL of one previously answered candidate, changing only parameter "
    "values.\n\n"
    "A candidate matches ONLY IF the new question asks for the same result shape:\n"
    "- the same grouping dimensions (the columns results are broken down by),\n"
    "- the same selected columns and metrics,\n"
    "- the same aggregation, ordering and row limit.\n\n"
    "The ONLY thing that may differ is the VALUE of a parameter listed under that "
    "candidate's Parameters (e.g. a different year, county or price threshold).\n\n"
    "If the new question adds, removes or changes ANY grouping dimension, column, "
    "metric, aggregation, sort or filter that is not merely a listed parameter "
    "value, it is NOT a match — return match_index null. For example, 'average "
    "price by county' and 'average price by county and town' are DIFFERENT "
    "(the grouping differs), so they must NOT match. When in doubt, return null.\n\n"
    "Respond with ONLY a JSON object, no prose:\n"
    '{"match_index": <1-based index or null>, '
    '"confidence": <0.0-1.0>, '
    '"params": {<param_name>: <value>, ...}}\n\n'
    "Set match_index to null and confidence to 0.0 if no candidate matches. "
    "Only fill params that appear in the chosen candidate's parameter list."
)


@dataclass
class AdjudicationResult:
    """Outcome of Tier-3 adjudication."""
    matched: bool
    template: Template | None = None
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    usage: Any = None


def _build_user_message(question: str, candidates: list[Template]) -> str:
    lines = [f"New question: {question}", "", "Candidates:"]
    for i, t in enumerate(candidates, start=1):
        lines.append(f"{i}. Question: {t.question}")
        lines.append(f"   SQL: {t.sql_template}")
        if t.param_defs:
            lines.append(f"   Parameters: {json.dumps(t.param_defs)}")
    return "\n".join(lines)


def _parse_response(text: str) -> dict[str, Any]:
    match = _JSON_RE.search(text)
    if not match:
        return {"match_index": None, "confidence": 0.0, "params": {}}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"match_index": None, "confidence": 0.0, "params": {}}


def adjudicate(
    api_key: str,
    question: str,
    candidates: list[Template],
    *,
    threshold: float = CACHE_THRESHOLD,
    model: str = MODEL_HAIKU,
) -> AdjudicationResult:
    """Ask Haiku whether a candidate matches; accept only above threshold.

    Returns a miss (matched=False) with no API call when there are no
    candidates.
    """
    if not candidates:
        return AdjudicationResult(matched=False)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _build_user_message(question, candidates)}],
    )

    parsed = _parse_response(response.content[0].text)
    usage = response.usage

    index = parsed.get("match_index")
    confidence = float(parsed.get("confidence", 0.0) or 0.0)
    params = parsed.get("params") or {}

    if (
        index is None
        or not isinstance(index, int)
        or index < 1
        or index > len(candidates)
        or confidence < threshold
    ):
        return AdjudicationResult(matched=False, confidence=confidence, usage=usage)

    return AdjudicationResult(
        matched=True,
        template=candidates[index - 1],
        params=params,
        confidence=confidence,
        usage=usage,
    )

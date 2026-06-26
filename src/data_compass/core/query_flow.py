"""
Core query pipeline — Phase 5 (tiered cache).

run_query() orchestrates the four-tier cache, minimising AI spend:

  Tier 1 — exact/normalised match     → zero API; reuses SQL + cached summary
  Tier 2 — FAISS semantic retrieval   → zero API; local embedding
  Tier 3 — Haiku adjudication         → cheap; confirms a candidate + params
  Tier 4 — Sonnet generation + store  → expensive; only on a genuine miss

After SQL is resolved it is executed against DuckDB, an auto-chart is chosen,
a one-paragraph summary is produced (reused on a Tier-1 hit), and a cost line
reflects exactly which models ran.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from data_compass.auth.key_router import (
    TIER_RECRUITER,
    get_recruiter_token_id,
    resolve_api_key,
)
from data_compass.auth.recruiter import check_access, get_token, increment_usage
from data_compass.cache.adjudicate import adjudicate
from data_compass.cache.exact import lookup_exact
from data_compass.cache.generate import generate_and_store, substitute
from data_compass.cache.semantic import EmbedFn, embed_question, retrieve
from data_compass.cache.store import get_templates_for_dataset, set_summary
from data_compass.config import MODEL_HAIKU, MODEL_SONNET
from data_compass.core.costing import build_cost_line, CostLine
from data_compass.data.loader import get_schema
from data_compass.llm.sql_prompt import build_schema_text
from data_compass.llm.summary import generate_summary
from data_compass.sql.guard import is_safe_sql
from data_compass.viz.autochart import pick_chart

# Allow importing data.registry without the data package being installed
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data.registry import get_dataset  # noqa: E402


@dataclass
class QueryResult:
    """Outcome of a single NL→SQL query execution."""
    sql: str
    dataframe: pd.DataFrame = field(default_factory=pd.DataFrame)
    error: str | None = None
    usage: Any = None
    chart: Any = None
    summary: str | None = None
    cost_line: CostLine | None = None
    cache_tier: str = "miss"  # 'exact' | 'semantic' | 'miss'


def _finalise(
    sql: str,
    conn: duckdb.DuckDBPyConnection,
    *,
    usages: list[tuple[str, Any]],
    cache_tier: str,
    api_key: str,
    question: str,
    cached_summary: str | None = None,
) -> tuple[QueryResult, pd.DataFrame | None, str | None]:
    """Execute SQL, build chart/summary/cost. Returns (result, df, summary)."""
    try:
        df: pd.DataFrame = conn.execute(sql).df()
    except Exception as exc:
        return (
            QueryResult(
                sql=sql, error=str(exc), cache_tier=cache_tier,
                cost_line=build_cost_line(usages),
            ),
            None,
            None,
        )

    chart = pick_chart(df)

    if cached_summary is not None:
        summary = cached_summary  # Tier-1 reuse: no extra API call
    else:
        summary, summary_usage = generate_summary(api_key, question, df)
        if summary_usage is not None:
            usages.append((MODEL_HAIKU, summary_usage))

    result = QueryResult(
        sql=sql,
        dataframe=df,
        chart=chart,
        summary=summary,
        cache_tier=cache_tier,
        cost_line=build_cost_line(usages),
    )
    return result, df, summary


def run_query(
    question: str,
    dataset_id: str,
    api_key: str,
    conn: duckdb.DuckDBPyConnection,
    cache_conn,
    *,
    embed_fn: EmbedFn | None = None,
    scope: str = "public",
    schema_text: str | None = None,
) -> QueryResult:
    """
    Run the full tiered NL→SQL pipeline for a single question.

    Always returns a QueryResult; never raises. Inspect ``.error`` for
    failures and ``.cache_tier`` for which tier served the query.

    ``schema_text`` may be pre-built and supplied directly (e.g. from an
    ERDDeclaration for uploaded datasets), bypassing the demo registry lookup.
    """
    if schema_text is None:
        entry = get_dataset(dataset_id)
        schema = get_schema(conn)
        schema_text = build_schema_text(schema, entry)

    # --- Tier 1: exact / normalised match (zero API) ---------------------
    exact = lookup_exact(cache_conn, dataset_id, question, scope=scope)
    if exact is not None:
        sql = substitute(exact.sql_template, {})
        if is_safe_sql(sql):
            result, _, _ = _finalise(
                sql, conn, usages=[], cache_tier="exact",
                api_key=api_key, question=question,
                cached_summary=exact.summary,
            )
            return result

    # --- Tier 2 + 3: semantic retrieval + Haiku adjudication -------------
    usages: list[tuple[str, Any]] = []
    templates = get_templates_for_dataset(cache_conn, dataset_id, scope=scope)
    if templates:
        query_vec = embed_question(question, embed_fn=embed_fn)
        candidates = [t for t, _ in retrieve(query_vec, templates)]
        adj = adjudicate(api_key, question, candidates)
        if adj.usage is not None:
            usages.append((MODEL_HAIKU, adj.usage))
        if adj.matched and adj.template is not None:
            sql = substitute(adj.template.sql_template, adj.params)
            if is_safe_sql(sql):
                result, _, _ = _finalise(
                    sql, conn, usages=usages, cache_tier="semantic",
                    api_key=api_key, question=question,
                )
                return result

    # --- Tier 4: Sonnet generation + store (expensive, on a miss) --------
    gen = generate_and_store(
        api_key, cache_conn, conn, question, dataset_id, schema_text,
        embed_fn=embed_fn, scope=scope,
    )
    if gen.usage is not None:
        usages.append((MODEL_SONNET, gen.usage))

    if gen.error == "unsafe":
        return QueryResult(
            sql=gen.sql, error="unsafe", cache_tier="miss",
            cost_line=build_cost_line(usages),
        )
    if gen.error is not None or not gen.sql:
        return QueryResult(
            sql=gen.sql, error=gen.error or "Generation failed.",
            cache_tier="miss", cost_line=build_cost_line(usages),
        )

    result, _, summary = _finalise(
        gen.sql, conn, usages=usages, cache_tier="miss",
        api_key=api_key, question=question,
    )
    # Backfill the cached summary so a later exact hit is truly zero-cost.
    if gen.stored and gen.template_id is not None and result.error is None:
        set_summary(cache_conn, gen.template_id, summary)
    return result


def run_gated_query(
    session: dict,
    auth_conn,
    question: str,
    dataset_id: str,
    conn: duckdb.DuckDBPyConnection,
    cache_conn,
    *,
    embed_fn: EmbedFn | None = None,
    owner_key: str | None = None,
    scope: str = "public",
    schema_text: str | None = None,
) -> QueryResult:
    """Tier-aware wrapper around :func:`run_query` (Phase 6).

    Resolves the correct API key for the session's tier, enforces the recruiter
    quota/expiry gate *before* any API call, runs the pipeline, and increments
    the recruiter's usage counter on a successful query. Blocked queries return a
    ``QueryResult`` with ``cache_tier == "blocked"`` and an error *code* (mapped
    to a localised message by the UI); no API call is made.
    """
    res = resolve_api_key(session, owner_key=owner_key)

    # Recruiter gate — evaluated before the key check so an expired/exhausted
    # recruiter sees the precise reason rather than a generic key error.
    if res.tier == TIER_RECRUITER:
        token_id = get_recruiter_token_id(session)
        token = get_token(auth_conn, token_id) if token_id is not None else None
        if token is None:
            return QueryResult(sql="", error="access_revoked", cache_tier="blocked")
        access = check_access(token)
        if not access.allowed:
            return QueryResult(
                sql="", error=f"blocked:{access.reason}", cache_tier="blocked"
            )

    if res.key is None:
        return QueryResult(sql="", error="no_key", cache_tier="blocked")

    result = run_query(
        question, dataset_id, res.key, conn, cache_conn,
        embed_fn=embed_fn, scope=scope,
        schema_text=schema_text,
    )

    # A successful query (cache hit or miss) consumes one of the recruiter's quota.
    if res.tier == TIER_RECRUITER and result.error is None:
        increment_usage(auth_conn, get_recruiter_token_id(session))

    return result

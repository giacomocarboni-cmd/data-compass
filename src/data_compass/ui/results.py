"""
Results panel — Phase 5.

render_results(result) displays:
  1. Generated SQL (code block)
  2. Result table (dataframe)
  3. Auto-chart (Plotly, if the result shape supports it)
  4. NL summary paragraph
  5. Cache-tier + cost / model transparency caption
"""
from __future__ import annotations

import streamlit as st

from data_compass.i18n import t

_CACHE_TIER_KEYS = {
    "exact": "query.cache_exact",
    "semantic": "query.cache_semantic",
    "miss": "query.cache_miss",
}


def _cost_caption(result) -> str:
    """Combine the cache-tier note with the model/cost line."""
    parts = []
    tier_key = _CACHE_TIER_KEYS.get(getattr(result, "cache_tier", "miss"))
    if tier_key:
        parts.append(t(tier_key))
    if result.cost_line is not None:
        parts.append(result.cost_line.label)
    return " · ".join(parts)


def render_results(result) -> None:
    """Render the full results panel for a QueryResult."""
    st.subheader(t("query.sql_header"))
    st.code(result.sql, language="sql")

    if result.error:
        if result.error == "unsafe":
            st.error(t("query.safety_blocked"))
        else:
            st.error(t("query.exec_error").format(error=result.error))
        if result.cost_line is not None:
            st.caption(_cost_caption(result))
        return

    st.subheader(t("query.results_header"))
    if result.dataframe is None or result.dataframe.empty:
        st.info(t("query.no_rows"))
    else:
        st.dataframe(result.dataframe, width="stretch", hide_index=True)

    if result.chart is not None:
        st.subheader(t("query.chart_header"))
        st.plotly_chart(result.chart, width="stretch")
        meta = getattr(result.chart.layout, "meta", None)
        if isinstance(meta, dict) and meta.get("top_n"):
            st.caption(
                t("query.chart_top_n").format(
                    shown=meta["top_n"], total=meta["total"], by=meta["by"]
                )
            )

    if result.summary:
        st.subheader(t("query.summary_header"))
        st.markdown(result.summary)

    st.caption(_cost_caption(result))

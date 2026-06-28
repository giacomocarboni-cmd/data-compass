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

import pandas as pd
import streamlit as st

from data_compass.i18n import t
from data_compass.viz.autochart import pick_chart

# Substrings that indicate a column holds a monetary value → £ prefix.
_MONEY_WORDS = frozenset({
    "price", "amount", "value", "cost", "revenue", "spend", "fee",
    "salary", "wage", "income", "payment", "charge", "earning",
    "turnover", "sale", "budget", "profit", "loss",
})

# Column names (exact) or suffixes that should NOT get a thousands separator
# because they are date-parts or identifiers (e.g. year 1990 → "1,990" looks wrong).
_DATE_PARTS = frozenset({"year", "month", "day", "hour", "quarter", "week"})
_ID_SUFFIXES = ("_id", "_uid", "_code", "_key", "_ref", "_no")


_MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _skip_fmt(col_lower: str) -> bool:
    return col_lower in _DATE_PARTS or any(col_lower.endswith(s) for s in _ID_SUFFIXES)


def _humanise(df: pd.DataFrame) -> pd.DataFrame:
    """Replace integer month columns (1–12) with abbreviated names, sorted correctly.

    Returns a new dataframe; the original is unchanged.
    """
    changed = False
    out = df.copy()
    for col in out.columns:
        if col.lower() != "month":
            continue
        if not pd.api.types.is_integer_dtype(out[col]):
            continue
        vals = set(out[col].dropna().astype(int))
        if not vals.issubset(_MONTH_NAMES.keys()):
            continue
        out = out.sort_values(col)
        out[col] = out[col].map(_MONTH_NAMES)
        changed = True
    return out if changed else df


def _styled(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Return a Styler with locale-style number and currency formatting."""
    fmt: dict[str, str] = {}
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        col_lower = col.lower().replace(" ", "_")
        if _skip_fmt(col_lower):
            continue
        if any(w in col_lower for w in _MONEY_WORDS):
            non_null = df[col].dropna()
            all_whole = len(non_null) > 0 and (non_null % 1 == 0).all()
            fmt[col] = "£{:,.0f}" if all_whole else "£{:,.2f}"
        elif pd.api.types.is_float_dtype(df[col]):
            non_null = df[col].dropna()
            all_whole = len(non_null) > 0 and (non_null % 1 == 0).all()
            fmt[col] = "{:,.0f}" if all_whole else "{:,.2f}"
        else:
            fmt[col] = "{:,.0f}"
    return df.style.format(fmt, na_rep="—") if fmt else df.style

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
        df = _humanise(result.dataframe)
        st.dataframe(_styled(df), use_container_width=True, hide_index=True)
        chart = pick_chart(df)
        if chart is not None:
            st.subheader(t("query.chart_header"))
            st.plotly_chart(chart, use_container_width=True)
            meta = getattr(chart.layout, "meta", None)
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

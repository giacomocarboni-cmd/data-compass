"""
Auto-chart selection from result shape — Phase 4, enhanced Phase 9+.

pick_chart(df) → plotly Figure | None

Rules:
  - date/datetime col + metric(s)
      → line chart; one line per metric when multiple metrics present
  - low-cardinality (≤20) categorical col + 1 metric
      → bar chart
  - low-cardinality categorical col + 2+ metrics
      → grouped bar chart
  - high-cardinality categorical col + 1 metric
      → top-20 bar (tagged via layout.meta so UI can caption it)
  - high-cardinality categorical col + 2+ metrics
      → scatter of top-20 rows (metric0 vs metric1, hover shows category)
  - integer year/month/day/hour cols are treated as categorical so that
      "SELECT year, AVG(price) GROUP BY year" yields a bar, not nothing
  - exactly 2 pure numeric cols (no categorical, no date)
      → scatter
  - anything else → None
"""
from __future__ import annotations

import warnings

import pandas as pd
import plotly.express as px

_CARDINALITY_LIMIT = 20

# Integer columns whose names suggest a date part — treated as categorical
# for charting so "year, avg_price" gives a bar rather than a scatter or None.
_DATE_PART_NAMES = frozenset({"year", "month", "day", "hour", "quarter", "week"})


def _is_date_col(col: pd.Series) -> bool:
    """Return True if the column holds date/datetime values."""
    if pd.api.types.is_datetime64_any_dtype(col):
        return True
    # pandas 3.0 uses StringDtype ("str"), not object, for string columns
    if not pd.api.types.is_string_dtype(col):
        return False
    sample = col.dropna()
    if sample.empty:
        return False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            pd.to_datetime(sample, errors="raise")
        return True
    except Exception:
        return False


def pick_chart(df: pd.DataFrame):
    """Return a Plotly figure or None when no appropriate chart type exists.

    Parameters
    ----------
    df: Query result dataframe.

    Returns
    -------
    plotly.graph_objects.Figure | None
    """
    if df is None or df.empty or len(df.columns) < 2:
        return None

    # Integer date-part columns (year, month, …) are categorical for charts.
    date_part_cols = {
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and c.lower() in _DATE_PART_NAMES
    }

    numeric_cols = [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and c not in date_part_cols
    ]
    if not numeric_cols:
        return None

    date_cols = [c for c in df.columns if _is_date_col(df[c])]
    cat_cols = [
        c for c in df.columns
        if c in date_part_cols
        or (not pd.api.types.is_numeric_dtype(df[c]) and not _is_date_col(df[c]))
    ]

    # ── Time series: one line per metric ─────────────────────────────────────
    if date_cols:
        y = numeric_cols if len(numeric_cols) > 1 else numeric_cols[0]
        return px.line(df, x=date_cols[0], y=y, markers=True)

    # ── Categorical dimension ─────────────────────────────────────────────────
    if cat_cols:
        x = cat_cols[0]
        total = df[x].nunique()

        if len(numeric_cols) == 1:
            y = numeric_cols[0]
            if total <= _CARDINALITY_LIMIT:
                return px.bar(df, x=x, y=y)
            # Too many categories — top-N bar tagged for the UI caption.
            top = df.nlargest(_CARDINALITY_LIMIT, y)
            fig = px.bar(top, x=x, y=y)
            fig.update_xaxes(categoryorder="total descending")
            fig.update_layout(meta={"top_n": _CARDINALITY_LIMIT, "total": int(total), "by": y})
            return fig

        # Multiple metrics
        if total <= _CARDINALITY_LIMIT:
            return px.bar(df, x=x, y=numeric_cols, barmode="group")

        # High cardinality + multiple metrics → scatter of top-N rows.
        top = df.nlargest(_CARDINALITY_LIMIT, numeric_cols[0])
        return px.scatter(top, x=numeric_cols[0], y=numeric_cols[1], hover_name=x)

    # ── Pure numeric (no categorical, no date): scatter of first two ─────────
    if len(numeric_cols) == 2:
        return px.scatter(df, x=numeric_cols[0], y=numeric_cols[1])

    return None

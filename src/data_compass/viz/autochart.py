"""
Auto-chart selection from result shape — Phase 4.

pick_chart(df) → plotly Figure | None

Rules:
  - 1 low-cardinality (≤20 unique) categorical col + ≥1 numeric col → bar chart
  - 1 high-cardinality categorical col + ≥1 numeric col → bar chart of the
    top-20 categories by the numeric value (the figure is tagged via
    ``layout.meta`` so the UI can caption it "top 20 of N")
  - 1 date/datetime col + ≥1 numeric col → line chart
  - anything else (all-numeric, <2 cols, empty) → None
"""
from __future__ import annotations

import warnings

import pandas as pd
import plotly.express as px

_CARDINALITY_LIMIT = 20


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

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return None

    date_cols = [c for c in df.columns if _is_date_col(df[c])]
    cat_cols = [
        c for c in df.columns
        if not pd.api.types.is_numeric_dtype(df[c]) and not _is_date_col(df[c])
    ]

    y = numeric_cols[0]

    if date_cols:
        return px.line(df, x=date_cols[0], y=y, markers=True)

    if cat_cols:
        x = cat_cols[0]
        total = df[x].nunique()
        if total <= _CARDINALITY_LIMIT:
            return px.bar(df, x=x, y=y)

        # Too many categories to plot them all — show the top-N by the metric
        # instead of bailing out, and tag the figure so the UI can say so.
        top = df.nlargest(_CARDINALITY_LIMIT, y)
        fig = px.bar(top, x=x, y=y)
        fig.update_xaxes(categoryorder="total descending")
        fig.update_layout(meta={"top_n": _CARDINALITY_LIMIT, "total": int(total), "by": y})
        return fig

    return None

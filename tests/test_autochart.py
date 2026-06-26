"""Tests for Step 4.1 — auto-chart selection from result shape."""
from __future__ import annotations

import pandas as pd
import pytest

from data_compass.viz.autochart import pick_chart


class TestBarChart:
    def test_categorical_plus_numeric_gives_bar(self):
        df = pd.DataFrame({"county": ["London", "Bristol", "Leeds"], "sales": [300, 200, 150]})
        fig = pick_chart(df)
        assert fig is not None
        assert fig.data[0].__class__.__name__ == "Bar"

    def test_low_cardinality_boundary_gives_bar(self):
        df = pd.DataFrame({
            "type": [f"T{i}" for i in range(20)],
            "count": range(20),
        })
        fig = pick_chart(df)
        assert fig is not None
        assert fig.data[0].__class__.__name__ == "Bar"

    def test_high_cardinality_gives_top_n_bar(self):
        # 102 categories → too many to plot all, so show the top 20 by value.
        df = pd.DataFrame({
            "county": [f"County {i}" for i in range(102)],
            "avg_price": range(102),
        })
        fig = pick_chart(df)
        assert fig is not None
        assert fig.data[0].__class__.__name__ == "Bar"
        # Only the top 20 are plotted...
        assert len(fig.data[0].x) == 20
        # ...the highest-valued ones, in descending order.
        assert list(fig.data[0].y) == list(range(101, 81, -1))
        # ...and the figure is tagged so the UI can caption the truncation.
        assert fig.layout.meta == {"top_n": 20, "total": 102, "by": "avg_price"}

    def test_cardinality_boundary_21_is_truncated(self):
        df = pd.DataFrame({
            "street": [f"Road {i}" for i in range(21)],
            "price": range(21),
        })
        fig = pick_chart(df)
        assert fig is not None
        assert len(fig.data[0].x) == 20
        assert fig.layout.meta["total"] == 21


class TestLineChart:
    def test_datetime_plus_numeric_gives_line(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2022-01", "2023-01", "2024-01"]),
            "rain_mm": [50.0, 62.5, 48.3],
        })
        fig = pick_chart(df)
        assert fig is not None
        # px.line produces a Scatter trace
        assert fig.data[0].__class__.__name__ == "Scatter"

    def test_date_string_col_gives_line(self):
        df = pd.DataFrame({
            "transfer_date": ["2024-01-15", "2024-02-20", "2024-03-10"],
            "price": [250000, 310000, 280000],
        })
        fig = pick_chart(df)
        assert fig is not None
        assert fig.data[0].__class__.__name__ == "Scatter"


class TestTableOnly:
    def test_empty_df_returns_none(self):
        assert pick_chart(pd.DataFrame()) is None

    def test_none_returns_none(self):
        assert pick_chart(None) is None

    def test_single_column_returns_none(self):
        df = pd.DataFrame({"price": [1, 2, 3]})
        assert pick_chart(df) is None

    def test_no_numeric_columns_returns_none(self):
        df = pd.DataFrame({"name": ["A", "B"], "type": ["X", "Y"]})
        assert pick_chart(df) is None

    def test_two_numeric_cols_no_cat_returns_none(self):
        df = pd.DataFrame({"price": [100, 200], "count": [5, 10]})
        assert pick_chart(df) is None

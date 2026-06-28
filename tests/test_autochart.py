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


class TestGroupedBar:
    def test_categorical_plus_two_numeric_gives_grouped_bar(self):
        df = pd.DataFrame({
            "county": ["London", "Bristol", "Leeds"],
            "avg_price": [350000, 250000, 180000],
            "transaction_count": [500, 300, 200],
        })
        fig = pick_chart(df)
        assert fig is not None
        assert all(t.__class__.__name__ == "Bar" for t in fig.data)
        assert len(fig.data) == 2  # one trace per metric

    def test_high_cardinality_two_numeric_gives_scatter(self):
        df = pd.DataFrame({
            "county": [f"County {i}" for i in range(50)],
            "avg_price": range(50),
            "count": range(50, 100),
        })
        fig = pick_chart(df)
        assert fig is not None
        assert fig.data[0].__class__.__name__ == "Scatter"


class TestMultiLine:
    def test_date_plus_two_numeric_gives_two_traces(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2022-01", "2023-01", "2024-01"]),
            "tmax_c": [10.2, 11.5, 9.8],
            "tmin_c": [4.4, 5.1, 3.9],
        })
        fig = pick_chart(df)
        assert fig is not None
        assert len(fig.data) == 2
        assert all(t.__class__.__name__ == "Scatter" for t in fig.data)


class TestScatter:
    def test_two_numeric_cols_gives_scatter(self):
        df = pd.DataFrame({"tmax_c": [10.2, 11.5, 9.8], "rain_mm": [50.0, 62.5, 48.3]})
        fig = pick_chart(df)
        assert fig is not None
        assert fig.data[0].__class__.__name__ == "Scatter"

    def test_three_pure_numeric_cols_returns_none(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
        assert pick_chart(df) is None


class TestDateParts:
    def test_year_int_col_treated_as_categorical(self):
        df = pd.DataFrame({"year": [2022, 2023, 2024], "avg_price": [280000, 295000, 310000]})
        fig = pick_chart(df)
        assert fig is not None
        assert fig.data[0].__class__.__name__ == "Bar"

    def test_month_int_col_treated_as_categorical(self):
        df = pd.DataFrame({"month": list(range(1, 13)), "avg_temp": [5.1, 5.8, 8.2, 11.0, 14.5, 17.3, 19.2, 19.0, 15.7, 11.4, 7.6, 5.3]})
        fig = pick_chart(df)
        assert fig is not None
        assert fig.data[0].__class__.__name__ == "Bar"


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

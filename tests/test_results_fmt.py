"""Unit tests for results table number formatting (_styled, _humanise helpers)."""

import pandas as pd
import pytest

from data_compass.ui.results import _humanise, _styled


def _rendered(df: pd.DataFrame, col: str) -> str:
    """Return the formatted string for the first value in col."""
    styler = _styled(df)
    # Export the format dict via the internal _display_funcs mapping.
    fmt_fn = styler._display_funcs.get((0, df.columns.get_loc(col)))
    if fmt_fn is None:
        return str(df[col].iloc[0])
    return fmt_fn(df[col].iloc[0])


def test_price_column_gets_gbp_prefix():
    df = pd.DataFrame({"price": [315000.0]})
    assert _rendered(df, "price").startswith("£")


def test_price_whole_number_no_decimals():
    df = pd.DataFrame({"price": [315000.0]})
    assert _rendered(df, "price") == "£315,000"


def test_price_fractional_keeps_decimals():
    df = pd.DataFrame({"price": [315000.5, 287500.0]})
    assert _rendered(df, "price") == "£315,000.50"


def test_integer_count_gets_thousands_separator():
    df = pd.DataFrame({"transaction_count": [12345]})
    assert _rendered(df, "transaction_count") == "12,345"


def test_float_column_two_decimal_places():
    df = pd.DataFrame({"tmax_c": [10.23]})
    assert _rendered(df, "tmax_c") == "10.23"


def test_year_column_not_formatted():
    df = pd.DataFrame({"year": [1990]})
    # year should not get a thousands separator — rendered as plain integer string
    result = _rendered(df, "year")
    assert "," not in result


def test_month_column_not_formatted():
    df = pd.DataFrame({"month": [1]})
    result = _rendered(df, "month")
    assert "," not in result


def test_float_whole_numbers_no_decimal():
    df = pd.DataFrame({"count_result": [42.0, 100.0]})
    assert _rendered(df, "count_result") == "42"


def test_nan_rendered_as_dash():
    df = pd.DataFrame({"price": [float("nan")]})
    assert _rendered(df, "price") == "—"


def test_average_price_gets_gbp():
    df = pd.DataFrame({"average_price": [250000.5]})
    assert _rendered(df, "average_price").startswith("£")


def test_id_suffix_not_formatted():
    df = pd.DataFrame({"property_id": [123456]})
    result = _rendered(df, "property_id")
    assert "," not in result


class TestHumanise:
    def test_month_integers_replaced_with_names(self):
        df = pd.DataFrame({"month": [1, 2, 3], "avg_temp": [5.1, 5.8, 8.2]})
        out = _humanise(df)
        assert list(out["month"]) == ["Jan", "Feb", "Mar"]

    def test_month_sorted_before_replacing(self):
        df = pd.DataFrame({"month": [3, 1, 2], "avg_temp": [8.2, 5.1, 5.8]})
        out = _humanise(df)
        assert list(out["month"]) == ["Jan", "Feb", "Mar"]

    def test_non_month_column_unchanged(self):
        df = pd.DataFrame({"year": [2022, 2023], "price": [100, 200]})
        out = _humanise(df)
        assert list(out["year"]) == [2022, 2023]

    def test_month_out_of_range_not_replaced(self):
        df = pd.DataFrame({"month": [0, 13], "val": [1, 2]})
        out = _humanise(df)
        assert list(out["month"]) == [0, 13]

    def test_returns_same_object_when_no_change(self):
        df = pd.DataFrame({"price": [100, 200]})
        out = _humanise(df)
        assert out is df

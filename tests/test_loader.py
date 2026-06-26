"""Unit tests for Step 2.2 — DuckDB loader & schema introspection."""
import pytest
from data_compass.data.loader import load_dataset, get_schema, ColumnInfo


class TestLoadDataset:
    def test_land_registry_loads_both_tables(self):
        conn = load_dataset("land_registry")
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        assert "transactions" in tables
        assert "properties" in tables

    def test_land_registry_transactions_has_rows(self):
        conn = load_dataset("land_registry")
        count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert count > 0

    def test_land_registry_properties_has_rows(self):
        conn = load_dataset("land_registry")
        count = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
        assert count > 0

    def test_uk_weather_loads_both_tables(self):
        conn = load_dataset("uk_weather")
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        assert "stations" in tables
        assert "observations" in tables

    def test_uk_weather_join_is_consistent(self):
        conn = load_dataset("uk_weather")
        orphans = conn.execute(
            "SELECT COUNT(*) FROM observations o "
            "LEFT JOIN stations s ON o.station_id = s.station_id "
            "WHERE s.station_id IS NULL"
        ).fetchone()[0]
        assert orphans == 0

    def test_unknown_dataset_raises(self):
        with pytest.raises(KeyError):
            load_dataset("does_not_exist")

    def test_returns_duckdb_connection(self):
        import duckdb
        conn = load_dataset("uk_weather")
        assert isinstance(conn, duckdb.DuckDBPyConnection)

    def test_each_call_returns_independent_connection(self):
        conn_a = load_dataset("land_registry")
        conn_b = load_dataset("land_registry")
        conn_a.execute("CREATE TABLE _test AS SELECT 1 AS x")
        # conn_b should not see _test
        tables_b = {
            r[0]
            for r in conn_b.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main'"
            ).fetchall()
        }
        assert "_test" not in tables_b


class TestGetSchema:
    def test_returns_dict_with_expected_tables(self):
        conn = load_dataset("land_registry")
        schema = get_schema(conn)
        assert "transactions" in schema
        assert "properties" in schema

    def test_column_info_is_namedtuple(self):
        conn = load_dataset("uk_weather")
        schema = get_schema(conn)
        first_col = schema["stations"][0]
        assert isinstance(first_col, ColumnInfo)
        assert hasattr(first_col, "name")
        assert hasattr(first_col, "dtype")
        assert hasattr(first_col, "nullable")

    def test_land_registry_transactions_expected_columns(self):
        conn = load_dataset("land_registry")
        schema = get_schema(conn)
        col_names = {c.name for c in schema["transactions"]}
        assert {"transaction_uid", "property_id", "price", "transfer_date"}.issubset(col_names)

    def test_weather_observations_expected_columns(self):
        conn = load_dataset("uk_weather")
        schema = get_schema(conn)
        col_names = {c.name for c in schema["observations"]}
        assert {"station_id", "year", "month", "tmax_c", "rain_mm"}.issubset(col_names)

    def test_dtype_is_nonempty_string(self):
        conn = load_dataset("uk_weather")
        schema = get_schema(conn)
        for cols in schema.values():
            for col in cols:
                assert isinstance(col.dtype, str) and col.dtype

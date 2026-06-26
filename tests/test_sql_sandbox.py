"""
Step 8.0 — DuckDB execution sandbox (runtime backstop to the SQL guard).

`harden_connection(conn)` disables filesystem/network access on a DuckDB
connection after its tables are loaded. These tests confirm:

  - already-loaded in-memory tables remain queryable;
  - a `read_csv_auto` / `read_text` over any path raises at execution time;
  - the lockdown cannot be reverted (`lock_configuration`);
  - `load_dataset` / `load_uploaded_dataset` return hardened connections.

No API calls are made anywhere in this file.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from data_compass.data.loader import (
    get_schema,
    load_dataset,
    load_uploaded_dataset,
)
from data_compass.sql.guard import harden_connection
from data_compass.upload.ingest import ParsedFile


# ---------------------------------------------------------------------------
# harden_connection in isolation
# ---------------------------------------------------------------------------

class TestHardenConnection:
    def test_loaded_table_still_queryable(self):
        conn = duckdb.connect(":memory:")
        conn.execute("CREATE TABLE t AS SELECT * FROM (VALUES (1), (2), (3)) AS v(x)")
        harden_connection(conn)
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 3

    def test_read_csv_auto_blocked_after_hardening(self, tmp_path):
        csv = tmp_path / "secret.csv"
        csv.write_text("a,b\n1,2\n")
        conn = duckdb.connect(":memory:")
        conn.execute("CREATE TABLE t AS SELECT 1 AS x")
        harden_connection(conn)
        with pytest.raises(duckdb.Error):
            conn.execute(f"SELECT * FROM read_csv_auto('{csv.as_posix()}')").fetchall()

    def test_read_text_blocked_after_hardening(self, tmp_path):
        f = tmp_path / "secret.txt"
        f.write_text("top secret")
        conn = duckdb.connect(":memory:")
        conn.execute("CREATE TABLE t AS SELECT 1 AS x")
        harden_connection(conn)
        with pytest.raises(duckdb.Error):
            conn.execute(f"SELECT * FROM read_text('{f.as_posix()}')").fetchall()

    def test_external_access_cannot_be_re_enabled(self):
        conn = duckdb.connect(":memory:")
        conn.execute("CREATE TABLE t AS SELECT 1 AS x")
        harden_connection(conn)
        with pytest.raises(duckdb.Error):
            conn.execute("SET enable_external_access = true")


# ---------------------------------------------------------------------------
# Loaders return hardened connections
# ---------------------------------------------------------------------------

class TestLoadersAreHardened:
    def test_load_dataset_connection_is_hardened(self, tmp_path):
        conn = load_dataset("land_registry")
        # Demo tables load and query fine...
        schema = get_schema(conn)
        assert schema  # non-empty
        # ...but file reads are now blocked.
        leak = tmp_path / "leak.csv"
        leak.write_text("a\n1\n")
        with pytest.raises(duckdb.Error):
            conn.execute(f"SELECT * FROM read_csv_auto('{leak.as_posix()}')").fetchall()

    def test_load_uploaded_dataset_connection_is_hardened(self, tmp_path):
        files = [
            ParsedFile("orders.csv", pd.DataFrame({"id": [1, 2], "amt": [10, 20]})),
            ParsedFile("customers.csv", pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})),
        ]
        conn = load_uploaded_dataset(files)
        # Both uploaded tables query fine...
        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 2
        assert conn.execute(
            "SELECT COUNT(*) FROM orders o JOIN customers c ON o.id = c.id"
        ).fetchone()[0] == 2
        # ...but file reads are blocked.
        leak = tmp_path / "leak.txt"
        leak.write_text("secret")
        with pytest.raises(duckdb.Error):
            conn.execute(f"SELECT * FROM read_text('{leak.as_posix()}')").fetchall()

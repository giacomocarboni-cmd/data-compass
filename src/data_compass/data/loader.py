"""
DuckDB loader and schema introspection for Data Compass demo datasets.

Public API
----------
load_dataset(dataset_id)  -> duckdb.DuckDBPyConnection
    Load all CSV tables for the named dataset into an in-process DuckDB
    connection and return it.

get_schema(conn)          -> dict[str, list[ColumnInfo]]
    Introspect the connection and return a mapping of table name → column list.

ColumnInfo                namedtuple(name, dtype, nullable)
"""
from __future__ import annotations

import sys
from collections import namedtuple
from pathlib import Path

import duckdb

from data_compass.sql.guard import harden_connection

# Allow importing data.registry without installing the data package
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data.registry import get_dataset  # noqa: E402

ColumnInfo = namedtuple("ColumnInfo", ["name", "dtype", "nullable"])


def load_uploaded_dataset(parsed_files: list) -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection from a list of ParsedFile objects.

    Each file's DataFrame becomes a table named after the file stem
    (via ``table_name_from_filename``).  This is the login-scoped counterpart
    to ``load_dataset`` for the demo registry.
    """
    # Import here to avoid a circular dependency at module level
    from data_compass.erd.infer import table_name_from_filename  # noqa: PLC0415

    conn = duckdb.connect(database=":memory:")
    for pf in parsed_files:
        table_name = table_name_from_filename(pf.name)
        conn.register("_upload_tmp", pf.df)
        conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM _upload_tmp")
        conn.unregister("_upload_tmp")
    harden_connection(conn)
    return conn


def load_dataset(dataset_id: str) -> duckdb.DuckDBPyConnection:
    """
    Load the named demo dataset into an in-process DuckDB connection.

    Each CSV file in the registry becomes a DuckDB table named after its
    registry key (e.g. ``transactions``, ``properties``).

    Returns
    -------
    duckdb.DuckDBPyConnection
        A fresh in-memory connection with all tables populated.
    """
    entry = get_dataset(dataset_id)
    conn = duckdb.connect(database=":memory:")

    for table_name, csv_path in entry["tables"].items():
        p = Path(csv_path)
        if not p.exists():
            raise FileNotFoundError(
                f"Dataset file missing for {dataset_id}.{table_name}: {csv_path}"
            )
        # DuckDB reads CSV with header detection; single quotes around path for safety
        conn.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto(?)",
            [str(p)],
        )

    harden_connection(conn)
    return conn


def get_schema(conn: duckdb.DuckDBPyConnection) -> dict[str, list[ColumnInfo]]:
    """
    Return a mapping of table_name → list of ColumnInfo for every table in conn.

    Parameters
    ----------
    conn:
        A DuckDB connection, typically obtained from ``load_dataset()``.

    Returns
    -------
    dict[str, list[ColumnInfo]]
        Keys are table names; values are ordered lists of column descriptors.
    """
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
    ]

    schema: dict[str, list[ColumnInfo]] = {}
    for table in tables:
        rows = conn.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = ? "
            "ORDER BY ordinal_position",
            [table],
        ).fetchall()
        schema[table] = [
            ColumnInfo(name=r[0], dtype=r[1], nullable=(r[2] == "YES"))
            for r in rows
        ]

    return schema

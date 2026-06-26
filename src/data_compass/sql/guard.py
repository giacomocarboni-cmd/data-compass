"""
Read-only SQL safety guard.

``is_safe_sql(sql)`` returns True only when the statement:
  1. Is a SELECT (or a WITH ... SELECT CTE) — no DML or DDL allowed.
  2. Does not contain any dangerous keyword as a whole word.
  3. Does not call a DuckDB file/network table function (read_csv, read_text,
     glob, …) or reference a remote URL scheme (Step 8.0 — file-exfiltration).
  4. Can be parsed by DuckDB's parser without a syntax error.

The guard is the trust boundary: the LLM is untrusted, and its only privileged
output (SQL) is re-validated here on *every* cache tier before execution. The
guard is intentionally conservative: when in doubt it returns False. It is
backed at runtime by ``harden_connection()``, which disables filesystem and
network access on the DuckDB connection itself — defence in depth, so even a
text-matching miss cannot read outside the loaded in-memory tables.
"""
from __future__ import annotations

import re

import duckdb

# ---------------------------------------------------------------------------
# Block list — whole-word regex for statements that must never execute
# ---------------------------------------------------------------------------

_BLOCKED_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE"
    r"|ATTACH|DETACH|COPY|EXPORT|IMPORT|CALL|EXECUTE|PRAGMA|INSTALL|LOAD)\b",
    re.IGNORECASE,
)

# DuckDB file/network table & scalar functions that read outside the loaded
# in-memory tables. A plain ``SELECT * FROM read_text('/etc/passwd')`` starts
# with SELECT and contains no blocked statement keyword, so it must be blocked
# here. Matched in *call* form (name followed by "(") so a like-named column
# does not trigger a false positive.
_BLOCKED_FUNC_PATTERN = re.compile(
    r"\b(read_csv_auto|read_csv|read_parquet|parquet_scan|read_json_auto"
    r"|read_json|read_ndjson|read_text|read_blob|sniff_csv|glob)\s*\(",
    re.IGNORECASE,
)

# Remote URL schemes inside string literals (httpfs / s3 / etc.). Defence in
# depth alongside the function blocklist and the runtime sandbox.
_BLOCKED_URL_PATTERN = re.compile(
    r"\b(https?|s3|gcs|gs|azure|az|hf|r2)://",
    re.IGNORECASE,
)

# A statement is allowed only if its first meaningful keyword is SELECT or WITH
_SELECT_RE = re.compile(r"^\s*(WITH|SELECT)\b", re.IGNORECASE)


def _strip_comments(sql: str) -> str:
    """Remove SQL line comments (--) and block comments (/* */)."""
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql.strip()


def is_safe_sql(sql: str) -> bool:
    """
    Return True if ``sql`` is a read-only SELECT statement that DuckDB
    can parse without a syntax error.

    Parameters
    ----------
    sql:
        The SQL string to validate.

    Returns
    -------
    bool
        True  → safe to execute.
        False → rejected (DML/DDL/unparseable/empty).
    """
    if not sql or not sql.strip():
        return False

    cleaned = _strip_comments(sql)

    # Rule 1: must start with SELECT or WITH
    if not _SELECT_RE.match(cleaned):
        return False

    # Rule 2: must not contain any blocked statement keywords
    if _BLOCKED_PATTERN.search(cleaned):
        return False

    # Rule 3: must not call a file/network function or reference a remote URL
    if _BLOCKED_FUNC_PATTERN.search(cleaned):
        return False
    if _BLOCKED_URL_PATTERN.search(cleaned):
        return False

    # Rule 4: DuckDB parse check — catch syntax errors
    # CatalogException (unknown table/column) is acceptable; the SQL is syntactically valid.
    try:
        probe = duckdb.connect(":memory:")
        probe.execute(f"EXPLAIN {cleaned}")
    except duckdb.ParserException:
        return False
    except Exception:
        # CatalogException, BinderException etc. — syntax is fine, schema mismatch only
        pass

    return True


# ---------------------------------------------------------------------------
# Runtime sandbox — defence in depth at the connection level
# ---------------------------------------------------------------------------

def harden_connection(conn: duckdb.DuckDBPyConnection) -> None:
    """Irreversibly disable filesystem and network access on a connection.

    Call this **after** all tables have been loaded (loading CSVs itself needs
    external access). In-memory tables already created remain fully queryable;
    any subsequent attempt to read a file or URL from SQL raises a DuckDB
    ``PermissionException``. ``lock_configuration`` then prevents the settings
    from being toggled back on by an injected ``SET`` statement.

    This is the runtime backstop to ``is_safe_sql()``: even if a crafted query
    slipped the text blocklist, it cannot read outside the loaded tables.
    """
    conn.execute("SET enable_external_access = false")
    conn.execute("SET lock_configuration = true")

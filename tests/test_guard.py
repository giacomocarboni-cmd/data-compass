"""Unit tests for Step 3.3 — Read-only SQL safety guard.

Extended in Step 8.0 with file/network-function and URL blocking.
"""
import pytest
from data_compass.sql.guard import is_safe_sql


class TestSafeSelects:
    def test_simple_select_is_safe(self):
        assert is_safe_sql("SELECT * FROM transactions") is True

    def test_select_with_where(self):
        assert is_safe_sql("SELECT price FROM transactions WHERE price > 100000") is True

    def test_select_with_aggregation(self):
        assert is_safe_sql(
            "SELECT county, AVG(price) FROM transactions GROUP BY county"
        ) is True

    def test_select_with_join(self):
        assert is_safe_sql(
            "SELECT t.price, p.county FROM transactions t "
            "JOIN properties p ON t.property_id = p.property_id"
        ) is True

    def test_with_cte_is_safe(self):
        assert is_safe_sql(
            "WITH ranked AS (SELECT county, AVG(price) AS avg_p FROM transactions "
            "GROUP BY county) SELECT * FROM ranked ORDER BY avg_p DESC"
        ) is True

    def test_leading_whitespace_ok(self):
        assert is_safe_sql("   SELECT 1") is True

    def test_multiline_select(self):
        assert is_safe_sql(
            "SELECT\n  county,\n  COUNT(*) AS n\nFROM transactions\nGROUP BY county"
        ) is True


class TestBlockedStatements:
    def test_delete_blocked(self):
        assert is_safe_sql("DELETE FROM transactions") is False

    def test_insert_blocked(self):
        assert is_safe_sql("INSERT INTO transactions VALUES (1, 2)") is False

    def test_update_blocked(self):
        assert is_safe_sql("UPDATE transactions SET price = 0") is False

    def test_drop_blocked(self):
        assert is_safe_sql("DROP TABLE transactions") is False

    def test_create_blocked(self):
        assert is_safe_sql("CREATE TABLE evil AS SELECT 1") is False

    def test_alter_blocked(self):
        assert is_safe_sql("ALTER TABLE transactions ADD COLUMN x INT") is False

    def test_truncate_blocked(self):
        assert is_safe_sql("TRUNCATE TABLE transactions") is False

    def test_attach_blocked(self):
        assert is_safe_sql("ATTACH ':memory:' AS db2") is False

    def test_copy_blocked(self):
        assert is_safe_sql("COPY transactions TO '/tmp/out.csv'") is False

    def test_pragma_blocked(self):
        assert is_safe_sql("PRAGMA database_list") is False


class TestInlineBlockedKeywords:
    def test_select_with_hidden_delete(self):
        # Subquery containing DELETE should still be rejected
        assert is_safe_sql(
            "SELECT * FROM (DELETE FROM transactions RETURNING *)"
        ) is False

    def test_comment_hiding_drop(self):
        # Inline comment stripping must not let DROP sneak through
        # after comment removal the DROP keyword is still present
        sql = "SELECT 1; DROP TABLE transactions --"
        assert is_safe_sql(sql) is False


class TestBlockedFileFunctions:
    """Step 8.0 — file/network table functions inside a SELECT must be blocked."""

    def test_read_text_blocked(self):
        assert is_safe_sql("SELECT * FROM read_text('/etc/passwd')") is False

    def test_read_csv_auto_blocked(self):
        assert is_safe_sql("SELECT * FROM read_csv_auto('/tmp/x.csv')") is False

    def test_read_csv_blocked(self):
        assert is_safe_sql("SELECT * FROM read_csv('x.csv')") is False

    def test_read_parquet_blocked(self):
        assert is_safe_sql("SELECT * FROM read_parquet('x.parquet')") is False

    def test_parquet_scan_blocked(self):
        assert is_safe_sql("SELECT * FROM parquet_scan('x.parquet')") is False

    def test_read_json_blocked(self):
        assert is_safe_sql("SELECT * FROM read_json('x.json')") is False

    def test_read_blob_blocked(self):
        assert is_safe_sql("SELECT * FROM read_blob('x')") is False

    def test_glob_blocked(self):
        assert is_safe_sql("SELECT * FROM glob('/home/*')") is False

    def test_read_text_in_subquery_blocked(self):
        assert is_safe_sql(
            "SELECT (SELECT content FROM read_text('/etc/hosts'))"
        ) is False

    def test_read_text_with_spaces_before_paren_blocked(self):
        assert is_safe_sql("SELECT * FROM read_text ('/etc/passwd')") is False

    def test_install_blocked(self):
        assert is_safe_sql("SELECT 1; INSTALL httpfs") is False

    def test_load_blocked(self):
        assert is_safe_sql("SELECT 1; LOAD httpfs") is False

    def test_lookalike_column_not_blocked(self):
        # A column merely *named* like a function (no call parens) is fine.
        assert is_safe_sql("SELECT read_text FROM mytable") is True


class TestBlockedUrls:
    """Step 8.0 — remote URL schemes must be blocked."""

    def test_https_url_blocked(self):
        assert is_safe_sql(
            "SELECT * FROM read_parquet('https://evil.com/x.parquet')"
        ) is False

    def test_http_url_blocked(self):
        assert is_safe_sql("SELECT * FROM 'http://evil.com/x'") is False

    def test_s3_url_blocked(self):
        assert is_safe_sql("SELECT * FROM 's3://bucket/key'") is False


class TestUnparseable:
    def test_empty_string(self):
        assert is_safe_sql("") is False

    def test_whitespace_only(self):
        assert is_safe_sql("   ") is False

    def test_syntax_error_rejected(self):
        assert is_safe_sql("SELECT FROM WHERE") is False

    def test_garbage_rejected(self):
        assert is_safe_sql("not sql at all!!!") is False

    def test_unclosed_paren_rejected(self):
        assert is_safe_sql("SELECT (1 + 2") is False

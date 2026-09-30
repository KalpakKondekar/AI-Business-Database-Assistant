"""Tests for the parser-backed SQL safety boundary."""

from __future__ import annotations

import unittest

from tools.sql_validator import validate_sql


class SQLValidatorTests(unittest.TestCase):
    def assert_accepted(self, sql: str) -> None:
        result = validate_sql(sql)
        self.assertTrue(result.valid, result.error_message)
        self.assertEqual(result.status, "accepted")

    def assert_rejected(self, sql: str, error_code: str | None = None) -> None:
        result = validate_sql(sql)
        self.assertFalse(result.valid)
        self.assertEqual(result.status, "rejected")
        if error_code:
            self.assertEqual(result.error_code, error_code)

    def test_valid_select(self) -> None:
        self.assert_accepted("SELECT customer_id, customer_name FROM customers")

    def test_valid_aggregation(self) -> None:
        self.assert_accepted(
            "SELECT policy_status, COUNT(*) AS policy_count "
            "FROM policies GROUP BY policy_status"
        )

    def test_valid_join(self) -> None:
        self.assert_accepted(
            "SELECT c.customer_name, p.policy_number "
            "FROM customers c JOIN policies p ON p.customer_id = c.customer_id"
        )

    def test_valid_with_select(self) -> None:
        self.assert_accepted(
            "WITH active AS (SELECT * FROM policies WHERE policy_status = 'Active') "
            "SELECT COUNT(*) AS count FROM active"
        )

    def test_write_operations_are_rejected(self) -> None:
        for sql in (
            "INSERT INTO customers VALUES (99, 'Test')",
            "UPDATE customers SET city = 'Test'",
            "DELETE FROM customers",
            "DROP TABLE customers",
            "ALTER TABLE customers ADD COLUMN test TEXT",
            "TRUNCATE TABLE customers",
            "ATTACH DATABASE 'other.db' AS other",
            "DETACH DATABASE other",
            "PRAGMA user_version",
            "CREATE TABLE test (id INTEGER)",
            "REPLACE INTO customers VALUES (99, 'Test')",
            "VACUUM",
            "REINDEX",
        ):
            with self.subTest(sql=sql):
                self.assert_rejected(sql, "read_only_violation")

    def test_multiple_statements_are_rejected(self) -> None:
        self.assert_rejected(
            "SELECT customer_id FROM customers; DELETE FROM customers",
            "multiple_statements",
        )

    def test_empty_sql_is_rejected(self) -> None:
        self.assert_rejected("   ", "empty_sql")

    def test_invalid_sql_is_rejected(self) -> None:
        self.assert_rejected("SELECT FROM customers", "invalid_sql")

    def test_unapproved_table_is_rejected(self) -> None:
        self.assert_rejected(
            "SELECT name FROM sqlite_master",
            "unapproved_table",
        )

    def test_row_limit_is_enforced(self) -> None:
        self.assert_rejected(
            "SELECT * FROM policies LIMIT 101",
            "row_limit_exceeded",
        )


if __name__ == "__main__":
    unittest.main()

"""Tests for controlled database tools and read-only execution."""

from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import Mock, patch

from db.connection import get_connection
from tools.database_tools import (
    execute_read_only_query,
    get_active_policy_count,
    get_claim_summary,
    get_customer_summary,
    get_database_schema,
    get_policy_details,
)
from tools.schemas import DatabaseResultStatus, DatabaseToolResult


class DatabaseToolsTests(unittest.TestCase):
    def test_active_policy_count_uses_read_only_repository(self) -> None:
        result = get_active_policy_count()

        self.assertEqual(result.status, DatabaseResultStatus.SUCCESS)
        self.assertEqual(result.tool_name, "get_active_policy_count")
        self.assertEqual(result.columns, ["active_policy_count"])
        self.assertEqual(result.rows, [{"active_policy_count": 5}])
        self.assertEqual(result.row_count, 1)

    def test_valid_select_returns_structured_result(self) -> None:
        result = execute_read_only_query(
            "SELECT customer_id, customer_name FROM customers ORDER BY customer_id"
        )
        self.assertEqual(result.status, DatabaseResultStatus.SUCCESS)
        self.assertEqual(result.row_count, 6)
        self.assertEqual(result.tool_name, "execute_read_only_query")
        self.assertIn("customer_name", result.columns)
        self.assertIsNotNone(result.execution_time_ms)

    def test_valid_aggregation_and_join_execute(self) -> None:
        aggregation = execute_read_only_query(
            "SELECT policy_status, COUNT(*) AS count FROM policies GROUP BY policy_status"
        )
        self.assertEqual(aggregation.status, DatabaseResultStatus.SUCCESS)

        joined = execute_read_only_query(
            "SELECT c.customer_name, p.policy_number "
            "FROM customers c JOIN policies p ON p.customer_id = c.customer_id "
            "ORDER BY p.policy_id"
        )
        self.assertEqual(joined.row_count, 7)

    def test_q12_claim_amount_filter_returns_all_four_claims(self) -> None:
        result = execute_read_only_query(
            "SELECT * FROM claims WHERE claim_amount > 100000 ORDER BY claim_id"
        )

        self.assertEqual(result.row_count, 4)
        self.assertEqual(len(result.rows), 4)
        rejection = next(row for row in result.rows if row["claim_id"] == 7003)
        self.assertEqual(
            rejection["rejection_reason"],
            "Policy was not active on the date of claim",
        )

    def test_valid_with_select_executes(self) -> None:
        result = execute_read_only_query(
            "WITH active AS (SELECT * FROM policies WHERE policy_status = 'Active') "
            "SELECT COUNT(*) AS count FROM active"
        )
        self.assertEqual(result.rows[0]["count"], 5)

    def test_row_limit_behavior(self) -> None:
        result = execute_read_only_query(
            "SELECT policy_id FROM policies ORDER BY policy_id",
            max_rows=2,
        )
        self.assertEqual(result.row_count, 2)
        self.assertEqual(len(result.rows), 2)
        self.assertTrue(result.truncated)

    def test_rejected_delete_never_reaches_sqlite(self) -> None:
        connection_factory = Mock(side_effect=AssertionError("SQLite was opened"))
        with patch("db.repository.get_connection", connection_factory):
            result = execute_read_only_query("DELETE FROM customers;")

        self.assertEqual(result.status, DatabaseResultStatus.REJECTED)
        self.assertEqual(result.error_code, "read_only_violation")
        connection_factory.assert_not_called()

    def test_ambiguous_customer_requires_clarification(self) -> None:
        identity_result = DatabaseToolResult(
            status=DatabaseResultStatus.SUCCESS,
            tool_name="get_customer_summary",
            columns=["customer_id", "customer_name", "city", "state"],
            rows=[
                {"customer_id": 10, "customer_name": "Rahul", "city": "Mumbai", "state": "Maharashtra"},
                {"customer_id": 11, "customer_name": "Rahul", "city": "Pune", "state": "Maharashtra"},
            ],
            row_count=2,
        )
        with patch(
            "tools.database_tools.repository_execute_read_only_query",
            return_value=identity_result,
        ):
            result = get_customer_summary(customer_name="Rahul")

        self.assertEqual(result.status, DatabaseResultStatus.CLARIFICATION_REQUIRED)
        self.assertEqual(result.error_code, "ambiguous_customer")
        self.assertEqual(result.row_count, 2)

    def test_unknown_customer_returns_no_results(self) -> None:
        result = get_customer_summary(customer_name="Unknown Customer")
        self.assertEqual(result.status, DatabaseResultStatus.NO_RESULTS)
        self.assertEqual(result.error_code, "customer_not_found")

    def test_unknown_policy_returns_no_results(self) -> None:
        result = get_policy_details(policy_number="POL-9999-999")
        self.assertEqual(result.status, DatabaseResultStatus.NO_RESULTS)
        self.assertEqual(result.error_code, "policy_not_found")

    def test_policy_number_is_not_treated_as_policy_id(self) -> None:
        result = get_policy_details(policy_number="POL-2023-001")

        self.assertEqual(result.status, DatabaseResultStatus.SUCCESS)
        self.assertEqual(result.rows[0]["policy_number"], "POL-2023-001")
        self.assertEqual(result.rows[0]["policy_id"], 1001)
        self.assertEqual(result.rows[0]["annual_premium"], 25000)

    def test_unknown_claim_returns_no_results(self) -> None:
        result = get_claim_summary(claim_id=999999)
        self.assertEqual(result.status, DatabaseResultStatus.NO_RESULTS)
        self.assertEqual(result.error_code, "claim_not_found")

    def test_schema_contains_only_approved_application_details(self) -> None:
        schema = get_database_schema()
        self.assertEqual(
            set(schema["tables"]),
            {"customers", "agents", "policies", "premium_payments", "claims"},
        )
        self.assertNotIn("password", str(schema).lower())
        self.assertNotIn("api_key", str(schema).lower())

    def test_read_only_connection_is_enforced(self) -> None:
        connection = get_connection(read_only=True)
        try:
            self.assertEqual(connection.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM customers")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()

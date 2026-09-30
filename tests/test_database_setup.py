"""Verification tests for the Stage 1 database foundation."""

from __future__ import annotations

import unittest

from db.init_db import initialize_database
from db.repository import fetch_all, fetch_one, row_count, table_names


EXPECTED_TABLES = ["agents", "claims", "customers", "policies", "premium_payments"]
EXPECTED_COUNTS = {
    "customers": 6,
    "agents": 3,
    "policies": 7,
    "premium_payments": 7,
    "claims": 5,
}


class DatabaseSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_path = initialize_database()

    def test_database_exists_and_all_tables_are_present(self) -> None:
        self.assertTrue(self.database_path.exists())
        self.assertEqual(table_names(), EXPECTED_TABLES)

    def test_seed_row_counts(self) -> None:
        for table_name, expected_count in EXPECTED_COUNTS.items():
            with self.subTest(table=table_name):
                self.assertEqual(row_count(table_name), expected_count)

    def test_basic_select_queries_work(self) -> None:
        active_policy_count = fetch_one(
            "SELECT COUNT(*) AS count FROM policies WHERE policy_status = ?",
            ("Active",),
        )
        self.assertEqual(active_policy_count["count"], 5)

        mumbai_customers = fetch_all(
            "SELECT customer_name FROM customers WHERE city = ? ORDER BY customer_id",
            ("Mumbai",),
        )
        self.assertEqual(
            [row["customer_name"] for row in mumbai_customers],
            ["Aarav Sharma", "Sneha Patil"],
        )


if __name__ == "__main__":
    unittest.main()

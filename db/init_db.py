"""Initialize the local SQLite database from the assignment SQL files."""

from __future__ import annotations

import argparse
from pathlib import Path

from .connection import DATABASE_PATH, DATA_DIRECTORY, get_connection


DB_DIRECTORY = Path(__file__).resolve().parent
SCHEMA_PATH = DB_DIRECTORY / "schema.sql"
SEED_PATH = DB_DIRECTORY / "seed.sql"


def initialize_database() -> Path:
    """Create the schema and load seed data once, then return the DB path."""

    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    seed_sql = SEED_PATH.read_text(encoding="utf-8")

    with get_connection() as connection:
        connection.executescript(schema_sql)
        existing_rows = connection.execute(
            """
            SELECT COALESCE(SUM(row_count), 0)
            FROM (
                SELECT COUNT(*) AS row_count FROM customers
                UNION ALL SELECT COUNT(*) FROM agents
                UNION ALL SELECT COUNT(*) FROM policies
                UNION ALL SELECT COUNT(*) FROM premium_payments
                UNION ALL SELECT COUNT(*) FROM claims
            )
            """
        ).fetchone()[0]
        if existing_rows == 0:
            connection.executescript(seed_sql)
        connection.commit()

    return DATABASE_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    database_path = initialize_database()
    print(f"Initialized database: {database_path}")


if __name__ == "__main__":
    main()

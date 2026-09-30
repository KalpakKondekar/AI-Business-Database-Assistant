"""Small generic read helpers for the SQLite database.

Business-specific queries belong in the future database tools layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from time import perf_counter

from .connection import get_connection
from tools.schemas import DatabaseResultStatus, DatabaseToolResult
from tools.sql_validator import validate_sql


def fetch_all(
    query: str,
    parameters: Sequence[Any] | Mapping[str, Any] = (),
) -> list[dict[str, Any]]:
    """Execute a read query and return rows as dictionaries."""

    with get_connection(read_only=True) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def fetch_one(
    query: str,
    parameters: Sequence[Any] | Mapping[str, Any] = (),
) -> dict[str, Any] | None:
    """Execute a read query and return one row as a dictionary."""

    with get_connection(read_only=True) as connection:
        row = connection.execute(query, parameters).fetchone()
    return dict(row) if row is not None else None


def execute_read_only_query(
    query: str,
    parameters: Sequence[Any] | Mapping[str, Any] = (),
    *,
    tool_name: str = "execute_read_only_query",
    max_rows: int = 100,
) -> DatabaseToolResult:
    """Validate and execute one read-only query using a read-only connection.

    Validation happens before ``get_connection`` is called. This ordering is
    deliberate: rejected SQL must never reach SQLite.
    """

    validation = validate_sql(query, max_rows=max_rows)
    if not validation.valid:
        return DatabaseToolResult(
            status=DatabaseResultStatus.REJECTED,
            tool_name=tool_name,
            row_count=0,
            error_code=validation.error_code,
            error_message=validation.error_message,
        )

    started = perf_counter()
    try:
        with get_connection(read_only=True) as connection:
            cursor = connection.execute(query, parameters)
            raw_rows = cursor.fetchmany(max_rows + 1)
            truncated = len(raw_rows) > max_rows
            rows = raw_rows[:max_rows]
            columns = [column[0] for column in cursor.description or ()]
    except Exception as error:
        # Do not return SQLite messages because they may disclose local paths
        # or implementation details to a future UI or model.
        error_code = "database_error"
        if isinstance(error, ValueError):
            error_code = "invalid_parameters"
        return DatabaseToolResult(
            status=DatabaseResultStatus.ERROR,
            tool_name=tool_name,
            execution_time_ms=(perf_counter() - started) * 1000,
            error_code=error_code,
            error_message="The database query could not be executed.",
        )

    return DatabaseToolResult(
        status=(
            DatabaseResultStatus.SUCCESS
            if rows
            else DatabaseResultStatus.NO_RESULTS
        ),
        columns=columns,
        rows=[dict(row) for row in rows],
        row_count=len(rows),
        truncated=truncated,
        execution_time_ms=(perf_counter() - started) * 1000,
        tool_name=tool_name,
    )


def table_names() -> list[str]:
    """Return application table names in deterministic order."""

    rows = fetch_all(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    return [row["name"] for row in rows]


def row_count(table_name: str) -> int:
    """Return a row count for a known table name."""

    allowed_tables = set(table_names())
    if table_name not in allowed_tables:
        raise ValueError(f"Unknown table: {table_name}")
    result = fetch_one(f'SELECT COUNT(*) AS count FROM "{table_name}"')
    return int(result["count"]) if result else 0

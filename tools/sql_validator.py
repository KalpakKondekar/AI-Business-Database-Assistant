"""Parser-backed validation for SQL submitted to the read-only tool.

This module is intentionally independent of SQLite execution. Callers must
validate first and only execute when the returned result is accepted.
"""

from __future__ import annotations

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from .schemas import SQLValidationResult


APPROVED_TABLES = frozenset(
    {"customers", "agents", "policies", "premium_payments", "claims"}
)
DEFAULT_MAX_ROWS = 100


def _rejected(
    *,
    max_rows: int,
    error_code: str,
    error_message: str,
    tables: list[str] | None = None,
) -> SQLValidationResult:
    return SQLValidationResult(
        valid=False,
        status="rejected",
        max_rows=max_rows,
        tables=tables or [],
        error_code=error_code,
        error_message=error_message,
    )


def _literal_limit(expression: exp.Expression) -> int | None:
    limit = expression.args.get("limit")
    if limit is None:
        return None
    value = limit.args.get("expression")
    if isinstance(value, exp.Literal) and value.is_int:
        return int(value.this)
    return None


def validate_sql(sql: str, *, max_rows: int = DEFAULT_MAX_ROWS) -> SQLValidationResult:
    """Validate one read-only SQLite query without executing it."""

    if not isinstance(sql, str) or not sql.strip():
        return _rejected(
            max_rows=max_rows,
            error_code="empty_sql",
            error_message="SQL must not be empty.",
        )
    if not 1 <= max_rows <= DEFAULT_MAX_ROWS:
        return _rejected(
            max_rows=max_rows,
            error_code="invalid_row_limit",
            error_message=f"Maximum result size must be between 1 and {DEFAULT_MAX_ROWS}.",
        )

    try:
        statements = parse(sql, read="sqlite")
    except ParseError:
        return _rejected(
            max_rows=max_rows,
            error_code="invalid_sql",
            error_message="The SQL statement could not be parsed.",
        )

    if len(statements) != 1:
        return _rejected(
            max_rows=max_rows,
            error_code="multiple_statements",
            error_message="Only one SQL statement is allowed.",
        )

    statement = statements[0]
    if not isinstance(statement, exp.Select):
        return _rejected(
            max_rows=max_rows,
            error_code="read_only_violation",
            error_message="Only SELECT and WITH ... SELECT statements are allowed.",
        )
    if not statement.expressions:
        return _rejected(
            max_rows=max_rows,
            error_code="invalid_sql",
            error_message="The SELECT statement must contain a projection.",
        )

    cte_names = {
        cte.alias_or_name.lower()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }
    referenced_tables: set[str] = set()
    for table in statement.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name in cte_names:
            continue
        if table.db and table.db.lower() != "main":
            return _rejected(
                max_rows=max_rows,
                error_code="unapproved_table",
                error_message="Only approved application tables may be queried.",
            )
        referenced_tables.add(table_name)

    unknown_tables = sorted(referenced_tables - APPROVED_TABLES)
    if unknown_tables:
        return _rejected(
            max_rows=max_rows,
            error_code="unapproved_table",
            error_message="Only approved application tables may be queried.",
            tables=sorted(referenced_tables),
        )

    requested_limit = _literal_limit(statement)
    if requested_limit is not None and requested_limit > max_rows:
        return _rejected(
            max_rows=max_rows,
            error_code="row_limit_exceeded",
            error_message=f"The query limit cannot exceed {max_rows} rows.",
            tables=sorted(referenced_tables),
        )

    return SQLValidationResult(
        valid=True,
        status="accepted",
        normalized_sql=statement.sql(dialect="sqlite"),
        tables=sorted(referenced_tables),
        max_rows=max_rows,
    )

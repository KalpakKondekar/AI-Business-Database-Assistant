"""Deterministic, non-LLM database tools for the insurance schema."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from db.repository import execute_read_only_query as repository_execute_read_only_query

from .schemas import (
    ClaimLookup,
    CustomerLookup,
    DatabaseResultStatus,
    DatabaseToolResult,
    PaymentLookup,
    PolicyLookup,
    ReadOnlySQLRequest,
)


TModel = TypeVar("TModel", bound=BaseModel)


DATABASE_SCHEMA: dict[str, Any] = {
    "tables": {
        "customers": {
            "columns": [
                "customer_id",
                "customer_name",
                "date_of_birth",
                "city",
                "state",
                "email",
                "mobile_number",
                "customer_since",
            ],
            "business_meaning": "Customer master data and contact details.",
        },
        "agents": {
            "columns": [
                "agent_id",
                "agent_name",
                "branch_name",
                "city",
                "joining_date",
                "status",
            ],
            "business_meaning": "Insurance agent and branch information.",
        },
        "policies": {
            "columns": [
                "policy_id",
                "policy_number",
                "customer_id",
                "agent_id",
                "product_name",
                "policy_type",
                "sum_assured",
                "annual_premium",
                "policy_start_date",
                "policy_end_date",
                "policy_status",
            ],
            "business_meaning": "Insurance policies owned by customers and managed by agents. annual_premium is the annual premium associated with each policy.",
        },
        "premium_payments": {
            "columns": [
                "payment_id",
                "policy_id",
                "premium_due_date",
                "payment_date",
                "premium_amount",
                "payment_status",
                "payment_mode",
            ],
            "business_meaning": "Premium payment history for policies. premium_amount is the amount of an individual premium payment transaction, not the policy's annual premium.",
        },
        "claims": {
            "columns": [
                "claim_id",
                "policy_id",
                "claim_type",
                "claim_date",
                "claim_amount",
                "claim_status",
                "settlement_date",
                "rejection_reason",
            ],
            "business_meaning": "Insurance claims submitted against policies.",
        },
    },
    "relationships": [
        {"from": "policies.customer_id", "to": "customers.customer_id"},
        {"from": "policies.agent_id", "to": "agents.agent_id"},
        {"from": "premium_payments.policy_id", "to": "policies.policy_id"},
        {"from": "claims.policy_id", "to": "policies.policy_id"},
    ],
}


def get_database_schema() -> dict[str, Any]:
    """Return the approved schema without connection or filesystem details."""

    return {
        "status": DatabaseResultStatus.SUCCESS.value,
        "tool_name": "get_database_schema",
        **DATABASE_SCHEMA,
    }


def get_active_policy_count() -> DatabaseToolResult:
    """Return the number of policies whose status is Active.

    This is intentionally specialized so lightweight local models can select
    the operation without having to synthesize SQL for a common question.
    Execution still goes through the shared read-only repository boundary.
    """

    return _run_query(
        "SELECT COUNT(*) AS active_policy_count "
        "FROM policies WHERE policy_status = ?",
        ["Active"],
        tool_name="get_active_policy_count",
    )


def _invalid_input(tool_name: str, error: ValidationError) -> DatabaseToolResult:
    return DatabaseToolResult(
        status=DatabaseResultStatus.ERROR,
        tool_name=tool_name,
        error_code="invalid_input",
        error_message="The tool input is invalid.",
    )


def _coerce_model(
    model_type: type[TModel],
    value: TModel | Mapping[str, Any] | None,
    tool_name: str,
    keyword_values: Mapping[str, Any],
) -> TModel | DatabaseToolResult:
    if isinstance(value, model_type):
        return value
    payload = dict(value or {})
    payload.update(keyword_values)
    try:
        return model_type.model_validate(payload)
    except ValidationError as error:
        return _invalid_input(tool_name, error)


def _run_query(
    query: str,
    parameters: list[Any] | tuple[Any, ...],
    *,
    tool_name: str,
) -> DatabaseToolResult:
    return repository_execute_read_only_query(
        query,
        parameters,
        tool_name=tool_name,
    )


def get_customer_summary(
    lookup: CustomerLookup | Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> DatabaseToolResult:
    """Return one customer's policies, payments, and claims.

    Name matches are resolved first. Multiple matches produce a clarification
    result instead of selecting an arbitrary customer.
    """

    tool_name = "get_customer_summary"
    value = _coerce_model(CustomerLookup, lookup, tool_name, kwargs)
    if isinstance(value, DatabaseToolResult):
        return value

    identity_query = """
        SELECT customer_id, customer_name, city, state
        FROM customers
        WHERE (:customer_id IS NULL OR customer_id = :customer_id)
          AND (:customer_name IS NULL OR LOWER(customer_name) = LOWER(:customer_name))
          AND (:city IS NULL OR LOWER(city) = LOWER(:city))
        ORDER BY customer_id
    """
    identity_parameters = {
        "customer_id": value.customer_id,
        "customer_name": value.customer_name,
        "city": value.city,
    }
    identities = repository_execute_read_only_query(
        identity_query,
        identity_parameters,
        tool_name=tool_name,
    )
    if identities.status is DatabaseResultStatus.ERROR:
        return identities
    if not identities.rows:
        return identities.model_copy(
            update={
                "error_code": "customer_not_found",
                "error_message": "No matching customer was found in the available database.",
            }
        )
    if len(identities.rows) > 1:
        return identities.model_copy(
            update={
                "status": DatabaseResultStatus.CLARIFICATION_REQUIRED,
                "columns": ["customer_id", "customer_name", "city", "state"],
                "row_count": len(identities.rows),
                "error_code": "ambiguous_customer",
                "error_message": "Multiple customers match. Please provide a customer ID or city.",
            }
        )

    customer_id = identities.rows[0]["customer_id"]
    query = """
        SELECT
            c.customer_id, c.customer_name, c.city, c.state,
            c.email, c.mobile_number, c.customer_since,
            p.policy_id, p.policy_number, p.product_name, p.policy_type,
            p.sum_assured, p.annual_premium, p.policy_start_date,
            p.policy_end_date, p.policy_status,
            a.agent_id, a.agent_name,
            pp.payment_id, pp.premium_due_date, pp.payment_date,
            pp.premium_amount, pp.payment_status, pp.payment_mode,
            cl.claim_id, cl.claim_type, cl.claim_date, cl.claim_amount,
            cl.claim_status, cl.settlement_date, cl.rejection_reason
        FROM customers AS c
        LEFT JOIN policies AS p ON p.customer_id = c.customer_id
        LEFT JOIN agents AS a ON a.agent_id = p.agent_id
        LEFT JOIN premium_payments AS pp ON pp.policy_id = p.policy_id
        LEFT JOIN claims AS cl ON cl.policy_id = p.policy_id
        WHERE c.customer_id = ?
        ORDER BY p.policy_id, pp.payment_id, cl.claim_id
    """
    return _run_query(query, [customer_id], tool_name=tool_name)


def get_policy_details(
    lookup: PolicyLookup | Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> DatabaseToolResult:
    """Return policy details with its customer, agent, payments, and claims.

    Use ``policy_number`` for business identifiers such as ``POL-2023-001``
    and ``policy_id`` only when the user explicitly provides the numeric
    internal ID, such as ``1001``. Never transform a policy number into an ID.
    """

    tool_name = "get_policy_details"
    value = _coerce_model(PolicyLookup, lookup, tool_name, kwargs)
    if isinstance(value, DatabaseToolResult):
        return value

    query = """
        SELECT
            p.policy_id, p.policy_number, p.product_name, p.policy_type,
            p.sum_assured, p.annual_premium, p.policy_start_date,
            p.policy_end_date, p.policy_status,
            c.customer_id, c.customer_name, c.city, c.state,
            a.agent_id, a.agent_name,
            pp.payment_id, pp.premium_due_date, pp.payment_date,
            pp.premium_amount, pp.payment_status, pp.payment_mode,
            cl.claim_id, cl.claim_type, cl.claim_date, cl.claim_amount,
            cl.claim_status, cl.settlement_date, cl.rejection_reason
        FROM policies AS p
        JOIN customers AS c ON c.customer_id = p.customer_id
        LEFT JOIN agents AS a ON a.agent_id = p.agent_id
        LEFT JOIN premium_payments AS pp ON pp.policy_id = p.policy_id
        LEFT JOIN claims AS cl ON cl.policy_id = p.policy_id
        WHERE (:policy_id IS NULL OR p.policy_id = :policy_id)
          AND (:policy_number IS NULL OR p.policy_number = :policy_number)
        ORDER BY pp.payment_id, cl.claim_id
    """
    result = _run_query(
        query,
        {"policy_id": value.policy_id, "policy_number": value.policy_number},
        tool_name=tool_name,
    )
    if not result.rows and result.status is DatabaseResultStatus.NO_RESULTS:
        return result.model_copy(
            update={
                "error_code": "policy_not_found",
                "error_message": "No matching policy was found in the available database.",
            }
        )
    return result


def get_claim_summary(
    lookup: ClaimLookup | Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> DatabaseToolResult:
    """Return claims matching the supplied filters."""

    tool_name = "get_claim_summary"
    value = _coerce_model(ClaimLookup, lookup, tool_name, kwargs)
    if isinstance(value, DatabaseToolResult):
        return value

    clauses: list[str] = []
    parameters: list[Any] = []
    for field, column in (
        ("claim_id", "cl.claim_id"),
        ("policy_id", "cl.policy_id"),
        ("customer_id", "p.customer_id"),
        ("claim_status", "cl.claim_status"),
        ("claim_type", "cl.claim_type"),
    ):
        field_value = getattr(value, field)
        if field_value is not None:
            clauses.append(f"{column} = ?")
            parameters.append(field_value)
    if value.min_claim_amount is not None:
        clauses.append("cl.claim_amount > ?")
        parameters.append(value.min_claim_amount)

    query = """
        SELECT
            cl.claim_id, cl.policy_id, cl.claim_type, cl.claim_date,
            cl.claim_amount, cl.claim_status, cl.settlement_date,
            cl.rejection_reason, p.policy_number, p.customer_id,
            c.customer_name
        FROM claims AS cl
        JOIN policies AS p ON p.policy_id = cl.policy_id
        JOIN customers AS c ON c.customer_id = p.customer_id
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY cl.claim_id"
    result = _run_query(query, parameters, tool_name=tool_name)
    if not result.rows and result.status is DatabaseResultStatus.NO_RESULTS:
        return result.model_copy(
            update={
                "error_code": "claim_not_found",
                "error_message": "No matching claim was found in the available database.",
            }
        )
    return result


def get_payment_summary(
    lookup: PaymentLookup | Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> DatabaseToolResult:
    """Return premium payments matching the supplied filters."""

    tool_name = "get_payment_summary"
    value = _coerce_model(PaymentLookup, lookup, tool_name, kwargs)
    if isinstance(value, DatabaseToolResult):
        return value

    clauses: list[str] = []
    parameters: list[Any] = []
    for field, column in (
        ("payment_id", "pp.payment_id"),
        ("policy_id", "pp.policy_id"),
        ("customer_id", "p.customer_id"),
        ("payment_status", "pp.payment_status"),
        ("payment_mode", "pp.payment_mode"),
    ):
        field_value = getattr(value, field)
        if field_value is not None:
            clauses.append(f"{column} = ?")
            parameters.append(field_value)

    query = """
        SELECT
            pp.payment_id, pp.policy_id, pp.premium_due_date,
            pp.payment_date, pp.premium_amount, pp.payment_status,
            pp.payment_mode, p.policy_number, p.customer_id,
            c.customer_name
        FROM premium_payments AS pp
        JOIN policies AS p ON p.policy_id = pp.policy_id
        JOIN customers AS c ON c.customer_id = p.customer_id
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY pp.payment_id"
    return _run_query(query, parameters, tool_name=tool_name)


def execute_read_only_query(
    sql: str | ReadOnlySQLRequest,
    parameters: Mapping[str, Any] | list[Any] | tuple[Any, ...] | None = None,
    *,
    max_rows: int = 100,
) -> DatabaseToolResult:
    """Validate and execute a caller-provided read-only SQL query."""

    tool_name = "execute_read_only_query"
    try:
        if isinstance(sql, ReadOnlySQLRequest):
            request = sql
        else:
            request = ReadOnlySQLRequest(
                sql=sql,
                parameters={} if parameters is None else parameters,
                max_rows=max_rows,
            )
    except ValidationError as error:
        return _invalid_input(tool_name, error)

    return repository_execute_read_only_query(
        request.sql,
        request.parameters,
        tool_name=tool_name,
        max_rows=request.max_rows,
    )

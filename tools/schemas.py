"""Typed contracts shared by the controlled database tools."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatabaseResultStatus(str, Enum):
    SUCCESS = "success"
    NO_RESULTS = "no_results"
    CLARIFICATION_REQUIRED = "clarification_required"
    REJECTED = "rejected"
    ERROR = "error"


class CustomerLookup(BaseModel):
    """Supported identifiers and disambiguation fields for customers."""

    model_config = ConfigDict(extra="forbid")

    customer_id: int | None = Field(default=None, gt=0)
    customer_name: str | None = Field(default=None, min_length=1, max_length=100)
    city: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def require_lookup_value(self) -> "CustomerLookup":
        if self.customer_id is None and self.customer_name is None:
            raise ValueError("customer_id or customer_name is required")
        return self


class PolicyLookup(BaseModel):
    """Supported identifiers for a policy lookup.

    ``policy_id`` is the internal numeric database key. ``policy_number`` is
    the business-facing identifier and must be passed as text without
    converting it into a numeric ID.
    """

    model_config = ConfigDict(extra="forbid")

    policy_id: int | None = Field(
        default=None,
        gt=0,
        description="Internal numeric database ID, for example 1001. Do not derive this from a policy number.",
    )
    policy_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=30,
        description="Business policy number, for example POL-2023-001. Pass this value as text exactly as provided; never convert it to policy_id.",
    )

    @model_validator(mode="after")
    def require_lookup_value(self) -> "PolicyLookup":
        if self.policy_id is None and self.policy_number is None:
            raise ValueError("policy_id or policy_number is required")
        return self


class ClaimLookup(BaseModel):
    """Optional filters for claim summaries."""

    model_config = ConfigDict(extra="forbid")

    claim_id: int | None = Field(default=None, gt=0)
    policy_id: int | None = Field(default=None, gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    claim_status: str | None = Field(default=None, min_length=1, max_length=30)
    claim_type: str | None = Field(default=None, min_length=1, max_length=50)
    min_claim_amount: float | None = Field(default=None, ge=0)


class PaymentLookup(BaseModel):
    """Optional filters for premium payment summaries."""

    model_config = ConfigDict(extra="forbid")

    payment_id: int | None = Field(default=None, gt=0)
    policy_id: int | None = Field(default=None, gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    payment_status: str | None = Field(default=None, min_length=1, max_length=20)
    payment_mode: str | None = Field(default=None, min_length=1, max_length=30)


class ReadOnlySQLRequest(BaseModel):
    """Input contract for a caller requesting a read-only SQL query."""

    model_config = ConfigDict(extra="forbid")

    sql: str = Field(min_length=1, max_length=20_000)
    parameters: dict[str, Any] | list[Any] | tuple[Any, ...] = Field(default_factory=dict)
    max_rows: int = Field(default=100, ge=1, le=100)


class DatabaseToolResult(BaseModel):
    """Safe, serializable result returned by every database tool."""

    model_config = ConfigDict(extra="forbid")

    status: DatabaseResultStatus
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    truncated: bool = False
    execution_time_ms: float | None = Field(default=None, ge=0)
    tool_name: str
    error_code: str | None = None
    error_message: str | None = None


class SQLValidationResult(BaseModel):
    """Structured output from SQL validation; validation never executes SQL."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    status: Literal["accepted", "rejected"]
    normalized_sql: str | None = None
    tables: list[str] = Field(default_factory=list)
    max_rows: int
    error_code: str | None = None
    error_message: str | None = None

"""Single-agent LangGraph workflow for controlled database tool calling."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

from .llm import create_llm
from .prompts import SYSTEM_PROMPT
from .state import AgentState
from tools.database_tools import (
    execute_read_only_query,
    get_claim_summary,
    get_customer_summary,
    get_database_schema,
    get_active_policy_count,
    get_payment_summary,
    get_policy_details,
)
from tools.schemas import (
    ClaimLookup,
    CustomerLookup,
    PaymentLookup,
    PolicyLookup,
    ReadOnlySQLRequest,
)


class NoArguments(BaseModel):
    """Empty argument schema for the schema inspection tool."""


_DEBUG_REDACTED_FIELDS = {
    "customer_id",
    "customer_name",
    "city",
    "state",
    "email",
    "mobile_number",
    "date_of_birth",
    "policy_number",
}


def _redact_debug_value(value: Any) -> Any:
    """Keep temporary tool tracing useful without printing unnecessary PII."""

    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key in _DEBUG_REDACTED_FIELDS else _redact_debug_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_debug_value(item) for item in value]
    return value


def _debug_tool_call(tool_name: str, arguments: dict[str, Any], result: Any) -> None:
    """Print temporary, bounded tool-call diagnostics for local debugging."""

    result_value = (
        result.model_dump(mode="json")
        if isinstance(result, BaseModel)
        else result
    )
    print(f"[tool] name={tool_name}")
    print(f"[tool] arguments={json.dumps(_redact_debug_value(arguments), default=str)}")
    print(
        "[tool] result="
        + json.dumps(_redact_debug_value(result_value), default=str)
    )


def _json_result(result: Any) -> str:
    if hasattr(result, "model_dump_json"):
        return result.model_dump_json()
    return json.dumps(result, default=str)


def _schema_tool() -> str:
    result = get_database_schema()
    _debug_tool_call("get_database_schema", {}, result)
    return _json_result(result)


def _active_policy_count_tool() -> str:
    result = get_active_policy_count()
    _debug_tool_call("get_active_policy_count", {}, result)
    return _json_result(result)


def _customer_tool(
    customer_id: int | None = None,
    customer_name: str | None = None,
    city: str | None = None,
) -> str:
    arguments = {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "city": city,
    }
    result = get_customer_summary(
        CustomerLookup(
            customer_id=customer_id,
            customer_name=customer_name,
            city=city,
        )
    )
    _debug_tool_call("get_customer_summary", arguments, result)
    return _json_result(result)


def _policy_tool(
    policy_id: int | None = None,
    policy_number: str | None = None,
) -> str:
    arguments = {"policy_id": policy_id, "policy_number": policy_number}
    result = get_policy_details(
        PolicyLookup(policy_id=policy_id, policy_number=policy_number)
    )
    _debug_tool_call("get_policy_details", arguments, result)
    return _json_result(result)


def _claim_tool(
    claim_id: int | None = None,
    policy_id: int | None = None,
    customer_id: int | None = None,
    claim_status: str | None = None,
    claim_type: str | None = None,
    min_claim_amount: float | None = None,
) -> str:
    arguments = {
        "claim_id": claim_id,
        "policy_id": policy_id,
        "customer_id": customer_id,
        "claim_status": claim_status,
        "claim_type": claim_type,
        "min_claim_amount": min_claim_amount,
    }
    result = get_claim_summary(
        ClaimLookup(
            claim_id=claim_id,
            policy_id=policy_id,
            customer_id=customer_id,
            claim_status=claim_status,
            claim_type=claim_type,
            min_claim_amount=min_claim_amount,
        )
    )
    _debug_tool_call("get_claim_summary", arguments, result)
    return _json_result(result)


def _payment_tool(
    payment_id: int | None = None,
    policy_id: int | None = None,
    customer_id: int | None = None,
    payment_status: str | None = None,
    payment_mode: str | None = None,
) -> str:
    arguments = {
        "payment_id": payment_id,
        "policy_id": policy_id,
        "customer_id": customer_id,
        "payment_status": payment_status,
        "payment_mode": payment_mode,
    }
    result = get_payment_summary(
        PaymentLookup(
            payment_id=payment_id,
            policy_id=policy_id,
            customer_id=customer_id,
            payment_status=payment_status,
            payment_mode=payment_mode,
        )
    )
    _debug_tool_call("get_payment_summary", arguments, result)
    return _json_result(result)


def _sql_tool(
    sql: str,
    parameters: dict[str, Any] | list[Any] | tuple[Any, ...] | None = None,
    max_rows: int = 100,
) -> str:
    arguments = {
        "sql": sql,
        "parameters": {} if parameters is None else parameters,
        "max_rows": max_rows,
    }
    result = execute_read_only_query(
        ReadOnlySQLRequest(
            sql=sql,
            parameters={} if parameters is None else parameters,
            max_rows=max_rows,
        )
    )
    _debug_tool_call("execute_read_only_query", arguments, result)
    return _json_result(result)


AGENT_TOOLS = [
    StructuredTool.from_function(
        func=_schema_tool,
        name="get_database_schema",
        description="Return the approved insurance database tables, columns, relationships, and business meanings. Use this when schema context is needed before constructing a query.",
        args_schema=NoArguments,
    ),
    StructuredTool.from_function(
        func=_active_policy_count_tool,
        name="get_active_policy_count",
        description=(
            "Return the total number of currently active insurance policies. "
            "Use this tool directly for questions such as 'How many active "
            "policies do we have?' or 'Count active policies'. It executes a "
            "fixed read-only database query and requires no arguments."
        ),
        args_schema=NoArguments,
    ),
    StructuredTool.from_function(
        func=_customer_tool,
        name="get_customer_summary",
        description=(
            "Retrieve a specific customer's profile and all related policy, "
            "payment, and claim information by customer ID or exact customer "
            "name. Prefer this tool when the user names a customer and asks "
            "for that customer's policy or claim details. If a name is "
            "ambiguous, the tool returns clarification_required; never choose "
            "a customer arbitrarily."
        ),
        args_schema=CustomerLookup,
    ),
    StructuredTool.from_function(
        func=_policy_tool,
        name="get_policy_details",
        description=(
            "Retrieve policy information for a specific policy. If the user "
            "provides a business policy number such as POL-2023-001, pass it "
            "as policy_number exactly as text. If the user explicitly provides "
            "a numeric internal database ID such as 1001, pass it as policy_id. "
            "Never convert a policy number into a numeric policy_id and never "
            "send both identifiers when only a policy number was provided. "
            "Includes the policy's customer, agent, payments, and claims."
        ),
        args_schema=PolicyLookup,
    ),
    StructuredTool.from_function(
        func=_claim_tool,
        name="get_claim_summary",
        description="Retrieve claims using claim, policy, customer, status, type, or minimum-amount filters. Use this for claim lookups and claim summaries.",
        args_schema=ClaimLookup,
    ),
    StructuredTool.from_function(
        func=_payment_tool,
        name="get_payment_summary",
        description="Retrieve premium payments using payment, policy, customer, status, or payment-mode filters.",
        args_schema=PaymentLookup,
    ),
    StructuredTool.from_function(
        func=_sql_tool,
        name="execute_read_only_query",
        description=(
            "Execute one validated read-only SQL SELECT query against the insurance "
            "database. MUST use this tool for analytical questions involving SUM, "
            "COUNT when no specialized count tool exists, AVG, GROUP BY, filtering "
            "across multiple tables, JOINs, totals, comparisons, or aggregations. "
            "For entity-level requests using 'each', 'per', or 'by', return one "
            "row per group and preserve all groups. For customer groups, join "
            "customers to policies on customer_id and return customer_name when "
            "names are requested. For agent groups, join agents to policies on "
            "agent_id and return agent_name when names are requested. Do not turn "
            "a grouped request into a highest, maximum, top, lowest, total, or "
            "single-row query. Ranking language such as 'highest', 'maximum', or "
            "'top' is distinct from an 'each' or 'by' request. "
            "Examples include total sum assured for active term policies, the "
            "product with the highest number of active policies, total annual "
            "premium collected by each agent, and claims greater than 100000. "
            "Use only the real schema: the policies table has policy_number, "
            "customer_id, agent_id, product_name, policy_type, sum_assured, "
            "annual_premium, policy_start_date, policy_end_date, and "
            "policy_status. For active term insurance use "
            "policy_status = 'Active' and policy_type = 'Term Insurance'. "
            "annual_premium is the policy-level annual premium from policies; "
            "premium_amount is an individual transaction from premium_payments. "
            "For total annual premium by agent, use SUM(p.annual_premium), join "
            "agents to policies on agent_id, and GROUP BY a.agent_name. Do not "
            "use premium_payments.premium_amount for annual premium questions "
            "unless the user explicitly asks about payment transactions. "
            "For example: SELECT SUM(sum_assured) FROM policies WHERE "
            "policy_status = 'Active' AND policy_type = 'Term Insurance'; "
            "SELECT COUNT(*) FROM policies WHERE policy_status = 'Active'; "
            "and SELECT SUM(annual_premium) FROM policies. "
            "The premium_payments table has payment_id, policy_id, "
            "premium_due_date, payment_date, premium_amount, payment_status, "
            "and payment_mode; overdue payments use payment_status = 'Overdue'. "
            "For 'Customers with overdue premium payments', join customers to "
            "policies on policies.customer_id = customers.customer_id, then join "
            "premium_payments on premium_payments.policy_id = policies.policy_id "
            "and filter premium_payments.payment_status = 'Overdue'. "
            "Example: SELECT c.customer_name, pp.payment_id, pp.premium_amount "
            "FROM customers AS c JOIN policies AS p ON p.customer_id = c.customer_id "
            "JOIN premium_payments AS pp ON pp.policy_id = p.policy_id "
            "WHERE pp.payment_status = 'Overdue'. "
            "A customer/payment join can also select c.customer_name and "
            "pp.payment_status using the same customers -> policies -> "
            "premium_payments relationships. "
            "The claims table has claim_id, policy_id, claim_type, claim_amount, "
            "claim_status, claim_date, settlement_date, and rejection_reason. "
            "For total claim amount for death claims, use SUM(claim_amount) and "
            "filter claim_type = 'Death Claim' for the current seeded data; do "
            "not add an amount filter unless the user asks for one. For claims "
            "with claim amount > 100000, use only claim_amount > 100000. For "
            "total death claims above 100000, use both claim_type = 'Death Claim' "
            "and claim_amount > 100000. `min_claim_amount` is not a database "
            "column. Map only constraints explicitly present in the current "
            "question; do not copy filters from another question. "
            "Use only tables and columns from the provided schema; never invent "
            "functions, term_insurance, active_policies, insurance_products, "
            "assured_amount, or active. If you do not know a table or column, do "
            "not invent one. "
            "Do not say the information is unavailable just because no specialized "
            "tool exists; query the approved database when it contains the data. "
            "Use get_active_policy_count only for a simple active-policy-count "
            "question. The application validates SQL and enforces read-only access "
            "before SQLite execution; this is not unrestricted SQL access."
        ),
        args_schema=ReadOnlySQLRequest,
    ),
]

MAX_TOOL_CALLS = 6


_FOLLOW_UP_REFERENCE = re.compile(
    r"\b(?:those|their|these)\b|\bthe above\b|\bwhat about them\b",
    re.IGNORECASE,
)


def _current_turn_messages(messages: list[Any]) -> list[Any]:
    """Scope model context to the current question unless it is an explicit follow-up."""

    latest_user_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        None,
    )
    if latest_user_index is None:
        return messages

    latest_question = str(messages[latest_user_index].content)
    if _FOLLOW_UP_REFERENCE.search(latest_question):
        return messages
    return messages[latest_user_index:]


def _model_node(model: Any):
    def call_model(state: AgentState) -> dict[str, list[AIMessage]]:
        scoped_messages = _current_turn_messages(state["messages"])
        messages = [SystemMessage(content=SYSTEM_PROMPT), *scoped_messages]
        response = model.invoke(messages)
        return {"messages": [response]}

    return call_model


def _route_after_model(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        tool_call_count = sum(
            isinstance(message, ToolMessage) for message in state["messages"]
        )
        if tool_call_count >= MAX_TOOL_CALLS:
            return "limit"
        return "tools"
    return END


def _limit_node(_: AgentState) -> dict[str, list[AIMessage]]:
    return {
        "messages": [
            AIMessage(
                content="I could not complete the database request within the allowed tool-call limit."
            )
        ]
    }


def build_graph(llm: Any | None = None):
    """Build and compile the single orchestrator/tool-node workflow."""

    model = llm or create_llm()
    model_with_tools = model.bind_tools(AGENT_TOOLS)

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", _model_node(model_with_tools))
    workflow.add_node("tools", ToolNode(AGENT_TOOLS))
    workflow.add_node("limit", _limit_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        _route_after_model,
        {"tools": "tools", "limit": "limit", END: END},
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("limit", END)
    return workflow.compile()

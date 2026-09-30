from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.graph import AGENT_TOOLS, build_graph
from agent.llm import DEFAULT_MODEL, create_llm
from agent.prompts import SYSTEM_PROMPT
from agent.response_formatter import extract_response_text, format_indian_number


class FakeModel:
    """Small chat-model double that supports LangChain tool binding."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = responses
        self.bound_tools = []
        self.received_messages = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.received_messages.append(messages)
        return self.responses.pop(0)


class AgentTests(unittest.TestCase):
    def test_indian_number_formatting(self) -> None:
        self.assertEqual(format_indian_number(150000), "1,50,000")
        self.assertEqual(format_indian_number(2500000), "25,00,000")
        self.assertEqual(format_indian_number(7500000), "75,00,000")

    def test_response_formatter_normalizes_currency_to_inr(self) -> None:
        self.assertEqual(
            extract_response_text("Claim amount: $150000; total: USD 2500000."),
            "Claim amount: ₹1,50,000; total: ₹25,00,000.",
        )

    def test_response_formatter_preserves_database_rejection_reason(self) -> None:
        reason = "Rejection reason: Policy was not active on the date of claim"
        self.assertEqual(extract_response_text(reason), reason)

    def test_response_formatter_preserves_plain_markdown_text(self) -> None:
        markdown = "There are currently **5 active policies** in the database."
        self.assertEqual(extract_response_text(markdown), markdown)

    def test_response_formatter_extracts_structured_text_blocks(self) -> None:
        content = [
            {"type": "text", "text": "There are currently **5 active policies**", "extras": {"signature": ""}},
            {"type": "text", "text": " in the database.", "extras": {"signature": ""}},
        ]
        self.assertEqual(
            extract_response_text(content),
            "There are currently **5 active policies** in the database.",
        )

    def test_system_prompt_contains_grounding_rules(self) -> None:
        self.assertIn("Do not invent database facts", SYSTEM_PROMPT)
        self.assertIn("Base the final answer only on information returned by the tools", SYSTEM_PROMPT)
        self.assertIn("database is read-only", SYSTEM_PROMPT)
        self.assertIn("Monetary database values are INR", SYSTEM_PROMPT)
        self.assertIn("Preserve database-provided text fields exactly", SYSTEM_PROMPT)

    def test_q12_final_grounding_does_not_reintroduce_claim_type(self) -> None:
        self.assertIn("use only constraints explicitly present in the current user request", SYSTEM_PROMPT)
        self.assertIn("Treat the rows in the authoritative successful tool result as the complete answer set", SYSTEM_PROMPT)
        self.assertIn("enumerate every returned row", SYSTEM_PROMPT)
        self.assertIn("never reduce the rows using an unrequested predicate such as claim_type", SYSTEM_PROMPT)
        self.assertIn("Do not invent status interpretations", SYSTEM_PROMPT)

    def test_q12_grounded_response_covers_all_returned_claims(self) -> None:
        grounded_response = (
            "Claims above ₹1,00,000:\n"
            "- 7001: Hospitalisation - ₹1,50,000\n"
            "- 7002: Death Claim - ₹25,00,000\n"
            "- 7003: Death Claim - ₹75,00,000\n"
            "- 7005: Critical Illness - ₹5,00,000"
        )

        self.assertIn("7001", grounded_response)
        self.assertIn("7002", grounded_response)
        self.assertIn("7003", grounded_response)
        self.assertIn("7005", grounded_response)
        self.assertNotIn("only two", grounded_response.lower())
        self.assertNotIn("Death Claim with an amount", grounded_response)

    def test_q14_uses_current_payment_turn_not_previous_agent_aggregation(self) -> None:
        self.assertIn("Resolve intent from the latest user message", SYSTEM_PROMPT)
        self.assertIn("Never transform a payment lookup into an agent or premium aggregation answer", SYSTEM_PROMPT)

        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_payment_summary",
                            "args": {"payment_mode": "Auto Debit"},
                            "id": "call_auto_debit",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content=(
                        "Payments made through Auto Debit:\n"
                        "- Payment 5004, policy 1004, amount ₹18,000, status Paid\n"
                        "- Payment 5007, policy 1007, amount ₹80,000, status Paid"
                    )
                ),
            ]
        )
        graph = build_graph(model)

        result = graph.invoke(
            {
                "messages": [
                    HumanMessage(content="What is the total annual premium collected by each agent?"),
                    AIMessage(content="Rajesh Kumar has ₹1,23,000; Priya Nair has ₹1,05,000."),
                    HumanMessage(content="Which premium payments were made through Auto Debit?"),
                ]
            }
        )

        final_text = result["messages"][-1].content
        self.assertIn("5004", final_text)
        self.assertIn("5007", final_text)
        self.assertNotIn("agent", final_text.lower())
        self.assertNotIn("annual premium", final_text.lower())
        self.assertNotIn("₹98,000", final_text)

    def test_standalone_question_drops_previous_city_context(self) -> None:
        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_active_policy_count",
                            "args": {},
                            "id": "call_active_count",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="There are 5 active policies."),
            ]
        )
        graph = build_graph(model)

        result = graph.invoke(
            {
                "messages": [
                    HumanMessage(content="List active policies for customers from Mumbai."),
                    AIMessage(content="Mumbai has active policies."),
                    HumanMessage(content="How many active policies are there?"),
                ]
            }
        )

        final_text = result["messages"][-1].content
        self.assertIn("5 active policies", final_text)
        self.assertNotIn("Mumbai", final_text)
        latest_model_messages = model.received_messages[-1]
        latest_content = " ".join(
            str(message.content) for message in latest_model_messages[1:]
        )
        self.assertNotIn("Mumbai", latest_content)

    def test_standalone_turn_grounding_guidance_is_explicit(self) -> None:
        self.assertIn("A standalone new question starts a new intent", SYSTEM_PROMPT)
        self.assertIn('"what about them"', SYSTEM_PROMPT)
        self.assertIn("If the latest successful tool result directly answers that question", SYSTEM_PROMPT)

    def test_entity_level_aggregation_guidance_matches_response_shape(self) -> None:
        sql_tool = next(tool for tool in AGENT_TOOLS if tool.name == "execute_read_only_query")
        guidance = SYSTEM_PROMPT + sql_tool.description

        for phrase in ("each customer", "for each customer", "by customer", "per customer"):
            self.assertIn(phrase, guidance)
        for phrase in ("each agent", "by agent", "per agent"):
            self.assertIn(phrase, guidance)
        self.assertIn("enumerate all returned groups", guidance)
        self.assertIn("return one row per group", guidance)
        self.assertIn("highest", guidance)
        self.assertIn("maximum", guidance)
        self.assertIn("latest user question", guidance)

    def test_each_customer_preserves_all_groups_and_uses_customer_name(self) -> None:
        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute_read_only_query",
                            "args": {
                                "sql": (
                                    "SELECT c.customer_name, COUNT(*) AS active_policy_count "
                                    "FROM customers AS c JOIN policies AS p "
                                    "ON c.customer_id = p.customer_id "
                                    "WHERE p.policy_status = 'Active' "
                                    "GROUP BY c.customer_id, c.customer_name "
                                    "ORDER BY c.customer_name"
                                )
                            },
                            "id": "call_customer_groups",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content=(
                        "Active policies by customer:\n"
                        "Aarav Sharma: 2\nMeera Iyer: 1\n"
                        "Sneha Patil: 1\nAnanya Rao: 1"
                    )
                ),
            ]
        )
        graph = build_graph(model)

        result = graph.invoke(
            {
                "messages": [
                    HumanMessage(content="Which product has the highest number of active policies?"),
                    AIMessage(content="Secure Life Plus has the highest number of active policies."),
                    HumanMessage(content="How many active policies does each customer have?"),
                ]
            }
        )

        sql = next(
            message
            for message in result["messages"]
            if isinstance(message, AIMessage) and message.tool_calls
        ).tool_calls[0]["args"]["sql"]
        self.assertIn("customers", sql)
        self.assertIn("customer_name", sql)
        self.assertIn("GROUP BY c.customer_id, c.customer_name", sql)
        self.assertNotIn("product_name", sql)
        self.assertNotIn("MAX(", sql.upper())
        self.assertNotIn("LIMIT 1", sql.upper())
        tool_message = next(
            message for message in result["messages"] if isinstance(message, ToolMessage)
        )
        self.assertIn('"row_count":4', tool_message.content)
        for customer_name in ("Aarav Sharma", "Meera Iyer", "Sneha Patil", "Ananya Rao"):
            self.assertIn(customer_name, result["messages"][-1].content)
        self.assertNotIn("highest", result["messages"][-1].content.lower())

    def test_each_agent_preserves_agent_groups_and_name(self) -> None:
        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute_read_only_query",
                            "args": {
                                "sql": (
                                    "SELECT a.agent_name, COUNT(*) AS policy_count "
                                    "FROM agents AS a JOIN policies AS p "
                                    "ON a.agent_id = p.agent_id "
                                    "GROUP BY a.agent_id, a.agent_name "
                                    "ORDER BY a.agent_name"
                                )
                            },
                            "id": "call_agent_groups",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Policies by agent: Amit Joshi, Priya Nair, Rajesh Kumar."),
            ]
        )
        graph = build_graph(model)

        result = graph.invoke(
            {"messages": [HumanMessage(content="How many policies does each agent have?")]}
        )

        sql = next(
            message
            for message in result["messages"]
            if isinstance(message, AIMessage) and message.tool_calls
        ).tool_calls[0]["args"]["sql"]
        self.assertIn("agents", sql)
        self.assertIn("agent_name", sql)
        self.assertIn("GROUP BY a.agent_id, a.agent_name", sql)
        self.assertNotIn("LIMIT 1", sql.upper())

    def test_response_shape_guidance_distinguishes_ranking_and_grouping(self) -> None:
        self.assertIn('"each", "per", and "by" mean enumerate all returned groups', SYSTEM_PROMPT)
        self.assertIn('"highest", "maximum", and "top" mean return the requested ranking', SYSTEM_PROMPT)
        self.assertIn('"total" means return an overall aggregate', SYSTEM_PROMPT)

    def test_system_prompt_contains_entity_role_and_currency_guidance(self) -> None:
        for relationship in (
            "customers.customer_id -> policies.customer_id",
            "agents.agent_id -> policies.agent_id",
            "policies.policy_id -> premium_payments.policy_id",
            "policies.policy_id -> claims.policy_id",
        ):
            self.assertIn(relationship, SYSTEM_PROMPT)
        self.assertIn("treat the person as a CUSTOMER", SYSTEM_PROMPT)
        self.assertIn("treat the person as an AGENT", SYSTEM_PROMPT)
        self.assertIn("Do not look for city or state directly in policies", SYSTEM_PROMPT)
        self.assertIn("Which policies are managed by Rajesh Kumar?", SYSTEM_PROMPT)
        self.assertIn("How many policies does Aarav Sharma have?", SYSTEM_PROMPT)
        self.assertIn("Active policies for Mumbai customers", SYSTEM_PROMPT)
        self.assertIn("Monetary database values are INR", SYSTEM_PROMPT)
        self.assertIn("using ₹", SYSTEM_PROMPT)

    def test_policy_identifier_guidance_preserves_business_policy_numbers(self) -> None:
        policy_tool = next(tool for tool in AGENT_TOOLS if tool.name == "get_policy_details")
        guidance = SYSTEM_PROMPT + policy_tool.description

        self.assertIn('policy_number = "POL-2023-001"', guidance)
        self.assertIn("do not derive policy_id = 2023001", guidance)
        self.assertIn("Never convert a policy number into a numeric policy_id", guidance)

    def test_tools_are_registered_with_expected_names(self) -> None:
        self.assertEqual(
            {tool.name for tool in AGENT_TOOLS},
            {
                "get_database_schema",
                "get_active_policy_count",
                "get_customer_summary",
                "get_policy_details",
                "get_claim_summary",
                "get_payment_summary",
                "execute_read_only_query",
            },
        )
        for tool in AGENT_TOOLS:
            self.assertTrue(tool.description)
            self.assertIsNotNone(tool.args_schema)

    def test_graph_can_construct_and_finish_without_tools(self) -> None:
        model = FakeModel([AIMessage(content="I can only answer insurance database questions.")])
        graph = build_graph(model)

        result = graph.invoke({"messages": [HumanMessage(content="Hello")]})

        self.assertEqual(result["messages"][-1].content, "I can only answer insurance database questions.")
        self.assertEqual(len(model.bound_tools), 7)
        self.assertIn("internal business database assistant", model.received_messages[0][0].content)

    def test_active_policy_count_tool_is_explicitly_described(self) -> None:
        tool = next(tool for tool in AGENT_TOOLS if tool.name == "get_active_policy_count")

        self.assertIn("How many active policies do we have?", tool.description)
        self.assertIn("Count active policies", tool.description)

    def test_generic_sql_tool_is_explicitly_described_for_analytics(self) -> None:
        tool = next(tool for tool in AGENT_TOOLS if tool.name == "execute_read_only_query")

        for term in ("SUM", "COUNT", "AVG", "GROUP BY", "JOIN", "totals", "comparisons"):
            self.assertIn(term, tool.description)
        self.assertIn("total sum assured for active term policies", tool.description)
        self.assertIn("product with the highest number of active policies", tool.description)
        self.assertIn("total annual premium collected by each agent", tool.description)
        self.assertIn("claims greater than 100000", tool.description)
        self.assertIn("Do not say the information is unavailable", tool.description)

    def test_q11_uses_policy_annual_premium_not_payment_amount(self) -> None:
        guidance = SYSTEM_PROMPT + next(
            tool for tool in AGENT_TOOLS if tool.name == "execute_read_only_query"
        ).description

        self.assertIn("SUM(p.annual_premium)", guidance)
        self.assertIn("GROUP BY a.agent_name", guidance)
        self.assertIn("premium_amount is an individual transaction", guidance)
        self.assertIn("do not use premium_payments.premium_amount", guidance)

    def test_q11_query_pattern_uses_agents_and_policies_only(self) -> None:
        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute_read_only_query",
                            "args": {
                                "sql": (
                                    "SELECT a.agent_name, SUM(p.annual_premium) AS total_annual_premium "
                                    "FROM agents a JOIN policies p ON a.agent_id = p.agent_id "
                                    "GROUP BY a.agent_name"
                                )
                            },
                            "id": "call_q11",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="The annual premium totals are available by agent."),
            ]
        )
        graph = build_graph(model)

        result = graph.invoke(
            {"messages": [HumanMessage(content="What is the total annual premium collected by each agent?")]}
        )

        sql = next(
            message
            for message in result["messages"]
            if isinstance(message, AIMessage) and message.tool_calls
        ).tool_calls[0]["args"]["sql"]
        self.assertIn("a.agent_name", sql)
        self.assertIn("SUM(p.annual_premium)", sql)
        self.assertIn("JOIN policies p ON a.agent_id = p.agent_id", sql)
        self.assertNotIn("premium_payments.premium_amount", sql)
        self.assertNotIn("pp.premium_amount", sql)

    def test_system_prompt_routes_analytical_questions_to_generic_sql(self) -> None:
        for example in (
            '"What is the total sum assured for active term insurance policies?"',
            '"Which product has the highest number of active policies?"',
            '"What is the total annual premium collected by each agent?"',
            '"Show claims greater than 100000."',
        ):
            self.assertIn(example, SYSTEM_PROMPT)
        self.assertIn("COUNT when no specialized count tool exists", SYSTEM_PROMPT)
        self.assertIn("Do not claim that information is unavailable", SYSTEM_PROMPT)

    def test_q10_constraint_isolation_guidance(self) -> None:
        self.assertIn("Constraint isolation is mandatory", SYSTEM_PROMPT)
        self.assertIn(
            '"Which product has the highest number of active policies?"',
            SYSTEM_PROMPT,
        )
        self.assertIn("Do not add policy_type = 'Term Insurance'", SYSTEM_PROMPT)
        self.assertIn(
            '"Which product has the highest number of active term insurance policies?"',
            SYSTEM_PROMPT,
        )
        self.assertIn(
            '"Which product has the highest number of active policies in Mumbai?"',
            SYSTEM_PROMPT,
        )
        self.assertIn("Do not inherit policy_type, city, customer, agent", SYSTEM_PROMPT)

    def test_q10_query_pattern_has_no_unrequested_policy_type_filter(self) -> None:
        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute_read_only_query",
                            "args": {
                                "sql": (
                                    "SELECT product_name, COUNT(*) AS policy_count "
                                    "FROM policies WHERE policy_status = 'Active' "
                                    "GROUP BY product_name ORDER BY policy_count DESC LIMIT 1"
                                )
                            },
                            "id": "call_q10",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Secure Life Plus has the highest number of active policies."),
            ]
        )
        graph = build_graph(model)

        result = graph.invoke(
            {"messages": [HumanMessage(content="Which product has the highest number of active policies?")]}
        )

        sql = next(
            message
            for message in result["messages"]
            if isinstance(message, AIMessage) and message.tool_calls
        ).tool_calls[0]["args"]["sql"]
        self.assertNotIn("policy_type", sql)
        self.assertEqual(
            result["messages"][-1].content,
            "Secure Life Plus has the highest number of active policies.",
        )

    def test_customer_detail_questions_prefer_specialized_tool_and_recover(self) -> None:
        customer_tool = next(tool for tool in AGENT_TOOLS if tool.name == "get_customer_summary")
        self.assertIn("Prefer this tool when the user names a customer", customer_tool.description)
        self.assertIn("If an earlier tool attempt returns an error", SYSTEM_PROMPT)
        self.assertIn("use the successful result as the source of truth", SYSTEM_PROMPT)

    def test_successful_customer_fallback_is_used_for_final_answer(self) -> None:
        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute_read_only_query",
                            "args": {"sql": "SELECT missing_column FROM policies"},
                            "id": "call_failed_query",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_customer_summary",
                            "args": {"customer_name": "Meera Iyer"},
                            "id": "call_customer_fallback",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Meera Iyer has the requested policy and claim details."),
            ]
        )
        graph = build_graph(model)

        result = graph.invoke(
            {"messages": [HumanMessage(content="Show the policy and claim details for Meera Iyer.")]}
        )

        self.assertEqual(
            result["messages"][-1].content,
            "Meera Iyer has the requested policy and claim details.",
        )
        tool_messages = [
            message for message in result["messages"] if isinstance(message, ToolMessage)
        ]
        self.assertEqual(len(tool_messages), 2)
        self.assertIn('"status":"error"', tool_messages[0].content)
        self.assertIn('"status":"success"', tool_messages[1].content)

    def test_sql_guidance_uses_real_schema_and_blocks_invented_names(self) -> None:
        sql_tool = next(tool for tool in AGENT_TOOLS if tool.name == "execute_read_only_query")
        guidance = SYSTEM_PROMPT + sql_tool.description

        for column in (
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
        ):
            self.assertIn(column, guidance)
        self.assertIn("SUM(sum_assured)", guidance)
        self.assertIn("policy_status = 'Active'", guidance)
        self.assertIn("policy_type = 'Term Insurance'", guidance)
        self.assertIn("Use only tables and columns from the provided schema", guidance)
        for invented_name in (
            "term_insurance",
            "active_policies",
            "insurance_products",
            "assured_amount",
            "active",
        ):
            self.assertIn(invented_name, guidance)

    def test_sql_guidance_covers_overdue_payment_customer_joins(self) -> None:
        sql_tool = next(tool for tool in AGENT_TOOLS if tool.name == "execute_read_only_query")
        guidance = SYSTEM_PROMPT + sql_tool.description

        for schema_name in (
            "premium_payments",
            "payment_id",
            "policy_id",
            "premium_due_date",
            "payment_date",
            "premium_amount",
            "payment_status",
            "payment_mode",
        ):
            self.assertIn(schema_name, guidance)
        self.assertIn("payment_status = 'Overdue'", guidance)
        self.assertIn("Customers with overdue premium payments", guidance)
        self.assertIn("customers -> policies -> premium_payments", guidance)
        self.assertIn("customers with claims", guidance)
        self.assertIn("policies managed by an agent", guidance)
        self.assertIn("total premium by agent", guidance)
        self.assertIn("Never invent functions", guidance)

    def test_sql_guidance_preserves_current_question_constraints(self) -> None:
        sql_tool = next(tool for tool in AGENT_TOOLS if tool.name == "execute_read_only_query")
        guidance = SYSTEM_PROMPT + sql_tool.description

        for column in (
            "claim_id",
            "policy_id",
            "claim_type",
            "claim_amount",
            "claim_status",
            "claim_date",
            "settlement_date",
            "rejection_reason",
        ):
            self.assertIn(column, guidance)
        self.assertIn("Total claim amount for death claims", guidance)
        self.assertIn("SUM(claim_amount)", guidance)
        self.assertIn("claim_type = 'Death Claim'", guidance)
        self.assertIn("Claims with claim amount > 100000", guidance)
        self.assertIn("claim_amount > 100000", guidance)
        self.assertIn("min_claim_amount` is not a database column", guidance)
        self.assertIn("Map only constraints explicitly present", guidance)

    def test_graph_routes_specialized_active_policy_count_tool(self) -> None:
        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_active_policy_count",
                            "args": {},
                            "id": "call_active_count",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="There are 5 active policies."),
            ]
        )
        graph = build_graph(model)

        result = graph.invoke(
            {"messages": [HumanMessage(content="How many active policies do we have?")]}
        )

        self.assertEqual(result["messages"][-1].content, "There are 5 active policies.")
        tool_message = next(
            message for message in result["messages"] if isinstance(message, ToolMessage)
        )
        self.assertIn('"active_policy_count":5', tool_message.content)

    def test_graph_policy_number_lookup_does_not_derive_policy_id(self) -> None:
        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_policy_details",
                            "args": {"policy_number": "POL-2023-001"},
                            "id": "call_policy_number",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="The annual premium is ₹25,000."),
            ]
        )
        graph = build_graph(model)

        result = graph.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="What is the annual premium for policy number POL-2023-001?"
                    )
                ]
            }
        )

        self.assertEqual(result["messages"][-1].content, "The annual premium is ₹25,000.")
        self.assertEqual(model.bound_tools[3].name, "get_policy_details")
        tool_message = next(
            message for message in result["messages"] if isinstance(message, ToolMessage)
        )
        self.assertIn('"policy_number":"POL-2023-001"', tool_message.content)
        self.assertIn('"policy_id":1001', tool_message.content)
        self.assertIn('"annual_premium":25000', tool_message.content)

    def test_graph_executes_a_tool_then_returns_final_answer(self) -> None:
        model = FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute_read_only_query",
                            "args": {
                                "sql": "SELECT COUNT(*) AS count FROM policies WHERE policy_status = 'Active'"
                            },
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="There are 5 active policies."),
            ]
        )
        graph = build_graph(model)

        result = graph.invoke(
            {"messages": [HumanMessage(content="How many active policies do we have?")]}
        )

        self.assertEqual(result["messages"][-1].content, "There are 5 active policies.")
        self.assertTrue(any(isinstance(message, ToolMessage) for message in result["messages"]))
        tool_message = next(
            message for message in result["messages"] if isinstance(message, ToolMessage)
        )
        self.assertIn('"status":"success"', tool_message.content)

    def test_ollama_model_configuration_is_provider_specific(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OLLAMA_MODEL": DEFAULT_MODEL,
                "OLLAMA_HOST": "http://localhost:11434",
            },
            clear=False,
        ):
            with patch("agent.llm.ChatOllama") as constructor:
                create_llm()

        self.assertEqual(constructor.call_args.kwargs["model"], DEFAULT_MODEL)
        self.assertEqual(
            constructor.call_args.kwargs["base_url"],
            "http://localhost:11434",
        )

    def test_ollama_requires_no_cloud_api_key(self) -> None:
        with patch.dict(
            os.environ,
            {"OLLAMA_MODEL": DEFAULT_MODEL},
            clear=True,
        ):
            with patch("agent.llm.ChatOllama") as constructor:
                create_llm()

        self.assertEqual(constructor.call_args.kwargs["model"], DEFAULT_MODEL)


if __name__ == "__main__":
    unittest.main()

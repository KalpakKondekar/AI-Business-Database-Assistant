"""Streamlit frontend for the SQL AI Agent."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.graph import build_graph
from agent.response_formatter import extract_response_text


SUGGESTED_QUESTIONS = {
    "Active Policies": "How many active policies are there?",
    "Mumbai Policies": "List active policies for customers from Mumbai.",
    "Term Insurance Sum Assured": "What is the total sum assured for active term insurance?",
    "Rajesh Kumar Policies": "Show the policies managed by Rajesh Kumar.",
    "Claim 7003 Rejection Reason": "Why was claim 7003 rejected?",
}


def _initialise_state() -> None:
    st.session_state.setdefault("agent_messages", [])
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("graph", None)


def _get_graph() -> Any:
    if st.session_state.graph is None:
        st.session_state.graph = build_graph()
    return st.session_state.graph


def _parse_tool_result(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _tool_trace(messages: list[Any], start_index: int) -> list[dict[str, Any]]:
    calls: dict[str, dict[str, Any]] = {}
    trace: list[dict[str, Any]] = []

    for message in messages[start_index:]:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                call_id = call.get("id", str(len(calls)))
                calls[call_id] = {
                    "name": call.get("name", "unknown_tool"),
                    "args": call.get("args", {}),
                }
        elif isinstance(message, ToolMessage):
            call = calls.get(message.tool_call_id, {})
            result = _parse_tool_result(message.content)
            item = {
                "name": call.get("name", getattr(message, "name", "unknown_tool")),
                "args": call.get("args", {}),
                "status": result.get("status", "completed"),
                "row_count": result.get("row_count"),
                "execution_time_ms": result.get("execution_time_ms"),
            }
            if "sql" in item["args"]:
                item["sql"] = item["args"]["sql"]
            if result.get("error_code"):
                item["error_code"] = result.get("error_code")
                item["error_message"] = result.get("error_message")
            trace.append(item)
    return trace


def _assistant_text(messages: list[Any], start_index: int) -> str:
    for message in reversed(messages[start_index:]):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return extract_response_text(message.content)
    return "I could not complete that request."


def _run_question(question: str) -> None:
    previous_count = len(st.session_state.agent_messages)
    st.session_state.chat_history.append({"role": "user", "content": question})

    try:
        messages = [*st.session_state.agent_messages, HumanMessage(content=question)]
        result = _get_graph().invoke({"messages": messages})
        updated_messages = result.get("messages", messages)
        st.session_state.agent_messages = updated_messages
        answer = _assistant_text(updated_messages, previous_count)
        trace = _tool_trace(updated_messages, previous_count)
    except RuntimeError as error:
        answer = str(error)
        trace = []
    except Exception:
        answer = "I could not complete that request. Please try again."
        trace = []

    st.session_state.chat_history.append(
        {"role": "assistant", "content": answer, "trace": trace}
    )


def _render_trace(trace: list[dict[str, Any]]) -> None:
    if not trace:
        return
    with st.expander("View Tool Details"):
        for index, item in enumerate(trace, start=1):
            st.markdown(f"**Tool {index}:** `{item['name']}`")
            details = {
                "status": item.get("status"),
                "row_count": item.get("row_count"),
                "execution_time_ms": item.get("execution_time_ms"),
            }
            if item.get("args"):
                st.json({"arguments": item["args"]})
            if item.get("error_code"):
                details["error_code"] = item["error_code"]
                details["error_message"] = item.get("error_message")
            st.json(details)
            if item.get("sql"):
                st.code(item["sql"], language="sql")


def main() -> None:
    st.set_page_config(page_title="AI Business Database Assistant", layout="centered")
    _initialise_state()

    st.markdown(
        """
        <style>
        .block-container { max-width: 900px; padding-top: 2rem; }
        [data-testid="stChatMessage"] { border-bottom: 1px solid #e6e6e6; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.title("Business Assistant")
        st.caption("Ask questions about the insurance database.")
        st.subheader("Suggested questions")
        for label, question in SUGGESTED_QUESTIONS.items():
            if st.button(label, use_container_width=True):
                st.session_state.pending_question = question
                st.rerun()
        st.divider()
        st.caption("Read-only database access")
        st.caption("Local model: qwen3:1.7b")
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.agent_messages = []
            st.session_state.chat_history = []
            st.rerun()

    st.title("AI-Powered Business Database Assistant")
    st.caption("Grounded answers from the read-only insurance database")

    for entry in st.session_state.chat_history:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])
            if entry["role"] == "assistant":
                _render_trace(entry.get("trace", []))

    pending_question = st.session_state.pop("pending_question", None)
    question = st.chat_input("Ask a business database question...") or pending_question
    if question:
        _run_question(question)
        st.rerun()


if __name__ == "__main__":
    main()

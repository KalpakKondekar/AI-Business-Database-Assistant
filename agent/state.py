"""Minimal state used by the Stage 3 LangGraph workflow."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Conversation messages passed between the model and tool nodes."""

    messages: Annotated[list[AnyMessage], add_messages]

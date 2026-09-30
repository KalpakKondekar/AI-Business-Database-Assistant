"""Local Ollama chat-model construction for the Stage 3 agent."""

from __future__ import annotations

import os

from langchain_ollama import ChatOllama


DEFAULT_MODEL = "qwen3:1.7b"


def create_llm() -> ChatOllama:
    """Create a local Ollama chat model with tool-calling support."""

    model_name = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
    ollama_host = os.getenv("OLLAMA_HOST")
    try:
        configuration = {
            "model": model_name,
            "temperature": 0,
        }
        if ollama_host:
            configuration["base_url"] = ollama_host
        return ChatOllama(**configuration)
    except Exception as error:
        raise RuntimeError(
            "The local Ollama chat model could not be initialized. "
            "Make sure Ollama is running and the model is available."
        ) from error

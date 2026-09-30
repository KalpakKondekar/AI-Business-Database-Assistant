"""Temporary proof-of-concept for Ollama Python tool calling."""

from __future__ import annotations

import json

from ollama import chat


MODEL = "qwen3:0.6b"


def get_active_policy_count() -> dict[str, int]:
    """Return a fixed value for testing tool invocation only."""

    return {"active_policy_count": 5}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_active_policy_count",
            "description": "Return the number of active insurance policies.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    }
]


def main() -> None:
    messages = [
        {
            "role": "user",
            "content": "How many active policies do we have?",
        }
    ]

    response = chat(model=MODEL, messages=messages, tools=TOOLS)
    print("Model response:")
    print(response.message.content)

    tool_calls = response.message.tool_calls or []
    if not tool_calls:
        print("No tool call was requested.")
        return

    messages.append(response.message)
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        tool_arguments = tool_call.function.arguments or {}
        print("Tool name:", tool_name)
        print("Tool arguments:", json.dumps(tool_arguments))

        if tool_name != "get_active_policy_count":
            raise RuntimeError(f"Unexpected tool requested: {tool_name}")

        tool_result = get_active_policy_count()
        print("Tool result:", json.dumps(tool_result))
        messages.append(
            {
                "role": "tool",
                "name": tool_name,
                "content": json.dumps(tool_result),
            }
        )

    final_response = chat(model=MODEL, messages=messages)
    print("Final model response:")
    print(final_response.message.content)


if __name__ == "__main__":
    main()

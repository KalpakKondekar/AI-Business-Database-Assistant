"""Helpers for rendering provider response content in the CLI."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


_CURRENCY_AMOUNT_PATTERN = re.compile(
    r"(?P<currency>\u20b9|\$|USD)\s*"
    r"(?P<amount>-?\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)


def format_indian_number(value: int | float | str) -> str:
    """Format a numeric amount using Indian digit grouping."""

    text = str(value).replace(",", "").strip()
    sign = ""
    if text.startswith("-"):
        sign, text = "-", text[1:]
    integer, separator, fraction = text.partition(".")
    if len(integer) <= 3:
        grouped = integer
    else:
        last_three = integer[-3:]
        prefix = integer[:-3]
        groups: list[str] = []
        while prefix:
            groups.insert(0, prefix[-2:])
            prefix = prefix[:-2]
        grouped = ",".join([*groups, last_three])
    return f"{sign}{grouped}{separator}{fraction}" if separator else f"{sign}{grouped}"


def _normalize_currency(text: str) -> str:
    """Normalize explicitly currency-marked amounts without changing other text."""

    def replace(match: re.Match[str]) -> str:
        return f"\u20b9{format_indian_number(match.group('amount'))}"

    return _CURRENCY_AMOUNT_PATTERN.sub(replace, text)


def extract_response_text(content: Any) -> str:
    """Return text content without changing Markdown formatting.

    Chat-model adapters may represent assistant content as a list of typed
    blocks, while other adapters return a plain string. Only text blocks are
    rendered; provider metadata is intentionally ignored.
    """

    if isinstance(content, str):
        return _normalize_currency(content)

    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, Mapping):
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
        if text_parts:
            return _normalize_currency("".join(text_parts))

    if isinstance(content, Mapping):
        text = content.get("text")
        if isinstance(text, str):
            return _normalize_currency(text)

    return _normalize_currency(str(content))

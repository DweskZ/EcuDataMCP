"""Helpers to return either human text or JSON from MCP tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from mcp.types import CallToolResult, TextContent


def normalize_format(fmt: str | None) -> str:
    value = (fmt or "text").strip().lower()
    return "json" if value == "json" else "text"


def render_output(
    data: Any,
    fmt: str = "text",
    text_builder: Callable[[Any], str] | None = None,
) -> str:
    """Return JSON string or text built from structured data."""
    mode = normalize_format(fmt)
    if mode == "json":
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if text_builder is not None:
        return text_builder(data)
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def render_structured(
    data: dict[str, Any],
    fmt: str = "text",
    text_builder: Callable[[Any], str] | None = None,
) -> CallToolResult:
    """Like render_output, but also attaches `data` as MCP structured_content.

    format="text"/"json" keeps controlling the legacy text block exactly as
    render_output always did (docs/MCP_ARCHITECTURE.md Phase 3 step 2 keeps
    `format` as legacy output during the transition) -- this only adds the
    same payload as structured_content alongside it, so a client that reads
    structured output doesn't need to re-parse the text block.
    """
    text = render_output(data, fmt, text_builder=text_builder)
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=data)

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


def cap_rows(
    payload: dict[str, Any],
    key: str,
    max_bytes: int,
    hint: str = "repetir la misma página con un page_size menor",
) -> dict[str, Any]:
    """Drop trailing rows of ``payload[key]`` until the JSON fits ``max_bytes``.

    Returns the payload unchanged when it already fits. Otherwise returns a
    copy whose ``metadatos.truncado`` states how many rows were kept and
    omitted, plus ``hint`` on how to get them. The omitted rows are not on the
    next page (paging advances by page_size), so the hint should point at a
    smaller page_size or a lighter view, never at page+1. At least one row is
    always kept.
    """
    rows = payload.get(key)
    if not isinstance(rows, list) or len(rows) < 2:
        return payload

    def size(n: int) -> int:
        trial = {**payload, key: rows[:n]}
        return len(json.dumps(trial, ensure_ascii=False, default=str).encode())

    if size(len(rows)) <= max_bytes:
        return payload
    # Bisect on the row count: size grows monotonically with the rows kept.
    low, high = 1, len(rows) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if size(mid) <= max_bytes:
            low = mid
        else:
            high = mid - 1
    metadatos = {
        **(payload.get("metadatos") or {}),
        "truncado": {
            "filas_devueltas": low,
            "filas_omitidas": len(rows) - low,
            "max_bytes": max_bytes,
            "como_pedir_el_resto": hint,
        },
    }
    return {**payload, key: rows[:low], "metadatos": metadatos}


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
    return CallToolResult(
        content=[TextContent(type="text", text=text)], structured_content=data
    )

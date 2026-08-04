"""Helpers to return either human text or JSON from MCP tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


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

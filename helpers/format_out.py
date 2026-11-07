"""Helpers to return either human text or JSON from MCP tools."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote, urlsplit

from mcp.types import CallToolResult, ResourceLink, TextContent

from helpers.response_contract import current_tool, ensure_response_metadata


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


# Ceiling for any structured response, after a tool's own caps
# (search_datasets keeps its tighter 60 KB). Large enough that ordinary
# results never hit it; past it the biggest list is trimmed and the
# truncation is declared in metadatos instead of relying on the client.
_DEFAULT_MAX_RESPONSE_BYTES = 200_000
_GENERIC_HINT = "pedir menos filas (limit, rows o page_size) o paginar con offset/page"

_TOTAL_KEYS = ("total", "total_entries", "total_features_en_capa", "total_resultados", "count")
_FILE_LIST_KEYS = ("archivos", "files", "resources")
_FILE_NAME_KEYS = ("titulo", "label", "name", "nombre", "title")
_MAX_RESOURCE_LINKS = 25
_MIME_BY_FORMAT = {
    "pdf": "application/pdf",
    "csv": "text/csv",
    "zip": "application/zip",
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "txt": "text/plain",
}


def max_response_bytes() -> int:
    raw = os.getenv("ECUADOR_MCP_MAX_RESPONSE_BYTES", "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else _DEFAULT_MAX_RESPONSE_BYTES


def _main_list_key(payload: dict[str, Any]) -> str | None:
    """The top-level list holding the most data: the one to page or trim."""
    best, best_size = None, -1
    for key, value in payload.items():
        if key == "metadatos" or not isinstance(value, list) or not value:
            continue
        size = len(json.dumps(value, ensure_ascii=False, default=str))
        if size > best_size:
            best, best_size = key, size
    return best


def cap_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the uniform byte ceiling to the payload's main list."""
    if isinstance((payload.get("metadatos") or {}).get("truncado"), dict):
        return payload  # the tool already capped itself
    key = _main_list_key(payload)
    if key is None:
        return payload
    return cap_rows(payload, key, max_response_bytes(), hint=_GENERIC_HINT)


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def derive_pagination(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Describe where the next page is, in one shape for every tool.

    Tools page in two styles: ``offset`` plus a total, or ``page`` plus a
    page count (or a total and ``page_size``). Only what the payload states
    is used; nothing is guessed, and ``None`` means the payload does not say.
    """
    key = _main_list_key(payload)
    count = len(payload[key]) if key else 0
    total = next((_int(payload.get(k)) for k in _TOTAL_KEYS if _int(payload.get(k)) is not None), None)
    hay_mas = payload.get("hay_mas") if isinstance(payload.get("hay_mas"), bool) else None

    offset = _int(payload.get("offset"))
    if offset is not None and (total is not None or hay_mas is not None):
        nxt = offset + count
        more = nxt < total if total is not None else bool(hay_mas)
        return {
            "estilo": "offset",
            "actual": offset,
            "devueltas": count,
            "total": total,
            "hay_mas": more,
            "siguiente": {"offset": nxt} if more else None,
        }

    page = _int(payload.get("page"))
    pages = _int(payload.get("pages"))
    page_size = _int(payload.get("page_size"))
    if pages is None and total is not None and page_size:
        pages = math.ceil(total / page_size)
    if page is not None and (pages is not None or hay_mas is not None):
        more = page < pages if pages is not None else bool(hay_mas)
        return {
            "estilo": "page",
            "actual": page,
            "devueltas": count,
            "total": total,
            "paginas": pages,
            "hay_mas": more,
            "siguiente": {"page": page + 1} if more else None,
        }
    return None


def resource_links(payload: dict[str, Any]) -> list[ResourceLink]:
    """MCP resource_link blocks for the file URLs a result lists.

    Lets a client fetch a listed file directly instead of asking for it to
    be inlined; the JSON payload is unchanged.
    """
    links: list[ResourceLink] = []
    seen: set[str] = set()
    for list_key in _FILE_LIST_KEYS:
        items = payload.get(list_key)
        if not isinstance(items, list):
            continue
        for item in items:
            if len(links) >= _MAX_RESOURCE_LINKS:
                return links
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            name = next(
                (item[k] for k in _FILE_NAME_KEYS if isinstance(item.get(k), str) and item[k].strip()),
                None,
            ) or unquote(urlsplit(url).path.rsplit("/", 1)[-1]) or url
            fmt = str(item.get("format") or item.get("formato") or "").lower().lstrip(".")
            links.append(
                ResourceLink(
                    type="resource_link",
                    uri=url,
                    name=name[:200],
                    mimeType=_MIME_BY_FORMAT.get(fmt),
                )
            )
    return links


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
    links: list[ResourceLink] = []
    if isinstance(data, dict):
        data = cap_response(data)
        data = ensure_response_metadata(data, current_tool.get())
        pagination = derive_pagination(data)
        if pagination is not None and "paginacion" not in data["metadatos"]:
            data = {**data, "metadatos": {**data["metadatos"], "paginacion": pagination}}
        links = resource_links(data)
    text = render_output(data, fmt, text_builder=text_builder)
    return CallToolResult(
        content=[TextContent(type="text", text=text), *links], structured_content=data
    )

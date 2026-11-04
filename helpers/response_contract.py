"""Stable metadata envelope for agent-facing JSON tool responses."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

CONTRACT_VERSION = "ecudatamcp.response.v1"

# Set by helpers.logging.log_tool around every tool call, so the generic
# envelope below can name the schema after the tool without each of the 85
# tools passing its own name to render_structured.
current_tool: ContextVar[str | None] = ContextVar("current_tool", default=None)

# Keys tools already use for provenance, in the order they are trusted.
_SOURCE_KEYS = ("source", "fuente_nombre", "fuente")
_SOURCE_URL_KEYS = ("url_fuente", "source_url")


def _first_str(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def ensure_response_metadata(
    payload: dict[str, Any], tool_name: str | None = None
) -> dict[str, Any]:
    """Give every structured response the ``metadatos`` envelope.

    Tools that already build the full envelope (the BCE and Supercías tools,
    through ``with_response_metadata``) are returned unchanged. For the rest,
    the envelope is filled from what the payload already says about itself:
    ``source``/``fuente`` and ``url_fuente``. Fields the tool does not know
    stay ``None`` rather than being guessed, and a partial ``metadatos``
    (for example ``truncado`` from ``cap_rows``) is kept.
    """
    existing = payload.get("metadatos")
    metadata = dict(existing) if isinstance(existing, dict) else {}
    if metadata.get("contrato") == CONTRACT_VERSION:
        return payload
    filled = {
        "contrato": CONTRACT_VERSION,
        "fuente": _first_str(payload, _SOURCE_KEYS),
        "url_fuente": _first_str(payload, _SOURCE_URL_KEYS),
        "consultado_en": datetime.now(UTC).isoformat(),
        "fecha_publicacion": None,
        "fecha_corte": None,
        "frescura": payload.get("frescura") if isinstance(payload.get("frescura"), str) else None,
        "esquema": {
            "nombre": f"ecudatamcp.{tool_name}" if tool_name else None,
            "campos_principales": [k for k in payload if k != "metadatos"],
        },
    }
    return {**payload, "metadatos": {**filled, **metadata}}


def with_response_metadata(
    payload: dict[str, Any],
    *,
    source: str,
    source_url: str | None,
    freshness: str,
    schema_name: str,
    schema_fields: list[str],
    consulted_at: str | None = None,
    published_at: str | None = None,
    cutoff: str | None = None,
) -> dict[str, Any]:
    """Add a backwards-compatible agent contract under ``metadatos``.

    Existing result fields remain at the top level.  This lets old clients
    continue reading a tool's established payload while agents can rely on a
    uniform location for provenance and freshness details.
    """
    existing = payload.get("metadatos")
    metadata = dict(existing) if isinstance(existing, dict) else {}
    metadata.update(
        {
            "contrato": CONTRACT_VERSION,
            "fuente": source,
            "url_fuente": source_url,
            "consultado_en": consulted_at or datetime.now(UTC).isoformat(),
            "fecha_publicacion": published_at,
            "fecha_corte": cutoff,
            "frescura": freshness,
            "esquema": {
                "nombre": schema_name,
                "campos_principales": schema_fields,
            },
        }
    )
    return {**payload, "metadatos": metadata}

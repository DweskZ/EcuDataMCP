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

# Reset to a fresh list by log_tool for every call. TtlCache.serve_stale
# appends to it when a source is down and a cached copy answers instead;
# tasks spawned during the call share the same list object.
stale_responses: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "stale_responses", default=None
)


def record_stale_response(cache_name: str, stored_at: float, exc: BaseException) -> None:
    notices = stale_responses.get()
    if notices is None:
        return
    notices.append(
        {
            "catalogo": cache_name,
            "datos_de": datetime.fromtimestamp(stored_at, UTC).isoformat(),
            "motivo": f"{type(exc).__name__}: {exc}"[:200],
        }
    )


def _apply_stale(payload: dict[str, Any]) -> dict[str, Any]:
    notices = stale_responses.get()
    if not notices:
        return payload
    metadata = dict(payload.get("metadatos") or {})
    metadata["frescura"] = "obsoleta"
    metadata["respuesta_obsoleta"] = {
        "datos_de": min(n["datos_de"] for n in notices),
        "catalogos": sorted({n["catalogo"] for n in notices}),
        "motivo": notices[0]["motivo"],
        "nota": "La fuente no respondió; se usó la última copia buena guardada.",
    }
    return {**payload, "metadatos": metadata}

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
        return _apply_stale(payload)
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
    return _apply_stale({**payload, "metadatos": {**filled, **metadata}})


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

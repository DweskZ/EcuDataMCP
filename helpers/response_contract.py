"""Stable metadata envelope for agent-facing JSON tool responses."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

CONTRACT_VERSION = "ecudatamcp.response.v1"


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

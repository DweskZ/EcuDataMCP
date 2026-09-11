"""Client for CEPALSTAT, ECLAC's (Comisión Económica para América Latina y
el Caribe) public statistics API (api-cepalstat.cepal.org) — a real REST
API confirmed live 2026-09-09/2026-09-10 (docs/RESEARCH.md § Vigésimo
quinta pasada), no authentication, documented by a genuine OpenAPI 3 spec
(`/apispec_1.json`, no `securityDefinitions`).

**NOT Ecuador-only.** CEPALSTAT is CEPAL's regional statistics catalog for
all of Latin America and the Caribbean (and, for many indicators, the rest
of the world) — 2,059 indicators confirmed live across a nested thematic
tree (Demográficos y sociales / Económicos / Ambientales / Temas
transversales). Ecuador is one queryable country among the catalog's ~145
country/territory/aggregate entries, not a separate Ecuador-specific
dataset. This module defaults every data pull to Ecuador (`pais="Ecuador"`)
because that is what this project is scoped to, but the underlying API
covers the whole region.

Two real endpoints under `/cepalstat/api/v1/`:

- `thematic-tree` — the full indicator catalog as a nested tree (theme >
  area > ... > indicator leaf). ~418 KB, confirmed live; cached with a long
  TTL since the catalog itself is stable.
- `indicator/{id}/dimensions` — one indicator's full dimension/member
  catalog (e.g. a "País" dimension with ~145 members, an "Años" dimension
  with ~200 members, sometimes a "Sexo" dimension) — used here only to
  resolve a country name to its numeric member id before requesting data,
  not exposed as its own tool.
- `indicator/{id}/data` — the actual observations, confirmed live against
  indicator 4788 ("Población total, según sexo"): an unfiltered call
  returns ~2.5 MB (every country, 1950-2100); passing `members=<país_id>`
  (confirmed: a single member id is enough — the API does not require one
  id per dimension) drops that to ~85 KB, just Ecuador's rows across every
  other free dimension (sex, year). Each row's dimensions come back as
  opaque `dim_<dimension_id>: <member_id>` pairs; this module decodes them
  back into `{dimension_name: member_name}` using the same response's own
  `dimensions` block (which lists every member of every dimension present
  in the indicator, not just the ones matching the filter) — otherwise a
  caller would see meaningless integers instead of "Sexo": "Mujeres".

Downloads go through helpers/csv_reader.download_bytes for the same 5 MB
cap and TLS handling every other client in this project uses, even though
this endpoint returns JSON rather than a file — CEPALSTAT has no separate
size-limiting mechanism of its own, and an unfiltered `/data` call on a
richer indicator than the one tested here could plausibly exceed a few MB.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlencode

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://api-cepalstat.cepal.org/cepalstat/api/v1"

# The indicator catalog changes rarely (CEPAL adds/retires indicators a few
# times a year at most) -- long TTL, same rationale as this project's other
# hand-maintained catalog pages.
_tree_cache = TtlCache(ttl_seconds=43200.0, max_entries=4)
_dimensions_cache = TtlCache(ttl_seconds=43200.0, max_entries=256)
_tree_lock = asyncio.Lock()

_PAIS_DIM_HINT = "pais"


def _build_url(path: str, **params: Any) -> str:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return f"{_BASE}{path}?{query}" if query else f"{_BASE}{path}"


async def _fetch_json(path: str, **params: Any) -> dict[str, Any]:
    url = _build_url(path, **params)
    logger.info("CEPALSTAT GET %s", url)
    content, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(
            f"La respuesta de {url} superó el límite de descarga — pide un "
            "indicador o filtro más acotado."
        )
    return json.loads(content)


def _flatten_tree(node: dict[str, Any], trail: list[str]) -> list[dict[str, Any]]:
    """Walk the nested thematic tree into a flat list of indicator leaves,
    each carrying the breadcrumb of area/sub-area names above it."""
    children = node.get("children") or []
    name = node.get("name", "")
    if "indicator_id" in node and not children:
        return [
            {
                "indicator_id": node["indicator_id"],
                "nombre": name,
                "area": " > ".join(trail),
            }
        ]
    leaves: list[dict[str, Any]] = []
    next_trail = [*trail, name] if name else trail
    for child in children:
        leaves.extend(_flatten_tree(child, next_trail))
    return leaves


async def _fetch_indicadores(lang: str) -> list[dict[str, Any]]:
    cache_key = f"tree:{lang}"
    cached = _tree_cache.get(cache_key)
    if cached is not None:
        return cached

    async with _tree_lock:
        cached = _tree_cache.get(cache_key)
        if cached is not None:
            return cached

        data = await _fetch_json("/thematic-tree", lang=lang)
        root = data.get("body") or {}
        indicadores = _flatten_tree(root, [])
        if indicadores:
            _tree_cache.set(cache_key, indicadores)
        return indicadores


async def search_indicadores(query: str = "", lang: str = "es") -> dict[str, Any]:
    """
    Search CEPALSTAT's full indicator catalog (2,059 indicators across
    Demográficos y sociales, Económicos, Ambientales, and Temas
    transversales) by name.

    Args:
        query: Free text matched (accent-insensitive) against the
            indicator's nombre or its area breadcrumb. Empty returns all
            indicators (large — prefer a query).
        lang: "es" (default) or "en"
    """
    indicadores = await _fetch_indicadores(lang)
    q = _strip(query)
    matched = [
        i
        for i in indicadores
        if not q or q in _strip(i["nombre"]) or q in _strip(i["area"])
    ]
    return {
        "total": len(matched),
        "total_catalogo": len(indicadores),
        "source": "CEPALSTAT — CEPAL",
        "url_fuente": "https://statistics.cepal.org/portal/cepalstat/",
        "indicadores": matched,
    }


async def _fetch_dimensions(indicator_id: int, lang: str) -> list[dict[str, Any]]:
    cache_key = f"{indicator_id}:{lang}"
    cached = _dimensions_cache.get(cache_key)
    if cached is not None:
        return cached

    data = await _fetch_json(f"/indicator/{indicator_id}/dimensions", lang=lang)
    dimensions = (data.get("body") or {}).get("dimensions") or []
    if dimensions:
        _dimensions_cache.set(cache_key, dimensions)
    return dimensions


def _find_pais_member_id(dimensions: list[dict[str, Any]], pais: str) -> int | None:
    q = _strip(pais)
    pais_dim = next(
        (d for d in dimensions if _PAIS_DIM_HINT in _strip(d.get("name", ""))), None
    )
    if pais_dim is None:
        return None
    members = pais_dim.get("members") or []
    exact = next((m for m in members if _strip(m.get("name", "")) == q), None)
    if exact is not None:
        return exact["id"]
    partial = next((m for m in members if q in _strip(m.get("name", ""))), None)
    return partial["id"] if partial is not None else None


def _decode_dimension_labels(
    dimensions: list[dict[str, Any]], lang: str
) -> dict[str, dict[int, str]]:
    """dim_<dimension_id> -> {member_id: member_name}, so a raw data row's
    opaque `dim_208: 229` can be turned into `"País": "Ecuador"`."""
    labels: dict[str, dict[int, str]] = {}
    for dim in dimensions:
        member_names = {m["id"]: m["name"] for m in dim.get("members") or []}
        # Strip CEPALSTAT's internal classification-scheme suffix
        # ("País__ESTANDAR" -> "País") -- confirmed live it denotes a
        # specific variant of the dimension, not reader-meaningful content.
        dim_name = dim.get("name", "").split("__", 1)[0]
        labels[f"dim_{dim['id']}"] = {"__dim_name__": dim_name, **member_names}
    return labels


def _decode_record(record: dict[str, Any], dim_labels: dict[str, dict[int, str]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in record.items():
        if key.startswith("dim_") and key in dim_labels:
            dim_name = dim_labels[key].get("__dim_name__", key)
            decoded[dim_name] = dim_labels[key].get(value, value)
        elif key == "value":
            decoded["valor"] = value
        elif key not in ("notes_ids",):
            decoded[key] = value
    return decoded


async def get_indicador(
    indicator_id: int, pais: str = "Ecuador", lang: str = "es"
) -> dict[str, Any]:
    """
    Fetch one CEPALSTAT indicator's observations, filtered to one country by
    default (Ecuador) to keep the payload small — the raw API returns every
    country in the region (and often the world) per indicator otherwise.

    Args:
        indicator_id: An "indicator_id" from search_indicadores.
        pais: Country name to filter to (accent-insensitive, e.g.
            "Ecuador", "Peru"). Empty string fetches every country the
            indicator covers — can be large (a few MB for a rich
            indicator).
        lang: "es" (default) or "en"
    """
    params: dict[str, Any] = {"lang": lang, "format": "json"}
    pais_filtrado = None
    if pais:
        dimensions_catalog = await _fetch_dimensions(indicator_id, lang)
        member_id = _find_pais_member_id(dimensions_catalog, pais)
        if member_id is None:
            raise ValueError(
                f"No se encontró el país '{pais}' entre las dimensiones del "
                f"indicador {indicator_id} (puede que este indicador no se "
                "desagregue por país)."
            )
        params["members"] = member_id
        pais_filtrado = pais

    data = await _fetch_json(f"/indicator/{indicator_id}/data", **params)
    body = data.get("body") or {}
    dim_labels = _decode_dimension_labels(body.get("dimensions") or [], lang)
    registros = [_decode_record(r, dim_labels) for r in body.get("data") or []]

    return {
        "indicator_id": indicator_id,
        "pais_filtrado": pais_filtrado,
        "metadata": body.get("metadata") or {},
        "total_registros": len(registros),
        "registros": registros,
        "fuentes": body.get("sources") or [],
        "notas": body.get("footnotes") or [],
        "source": "CEPALSTAT — CEPAL",
    }

"""Client for Secretaría de Gestión de Riesgos (SGR) ArcGIS services."""

from __future__ import annotations

import logging
from typing import Any
from unicodedata import category, normalize

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_TIMEOUT = 35.0
_COE2_SERVICE = (
    "https://sgrportal.gestionderiesgos.gob.ec/server/rest/services/COE2/MapServer"
)
_SAT_LAYER = (
    "https://sgrportal.gestionderiesgos.gob.ec/server/rest/services/SAT/MapServer/0"
)

_events_cache = TtlCache(ttl_seconds=300.0, max_entries=8)


def _strip(text: str) -> str:
    nfkd = normalize("NFKD", text or "")
    return "".join(c for c in nfkd if category(c) != "Mn").lower()


async def _get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
        timeout=_TIMEOUT,
    ) as session:
        logger.debug("SGR GET %s params=%s", url, params)
        resp = await session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def _coe2_layer_url() -> str:
    cached = _events_cache.get("coe2_layer_url")
    if isinstance(cached, str):
        return cached
    meta = await _get_json(_COE2_SERVICE, params={"f": "pjson"})
    layers = meta.get("layers") or []
    if not layers:
        raise RuntimeError("COE2 MapServer no expone layers")
    layer_id = layers[0].get("id", 0)
    url = f"{_COE2_SERVICE}/{layer_id}"
    _events_cache.set("coe2_layer_url", url)
    return url


async def list_risk_events(
    query: str = "",
    provincia: str = "",
    canton: str = "",
    evento: str = "",
    estado: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """
    Fetch COE emergency/risk events and filter client-side.

    The SGR layer snapshot name changes over time; we resolve layer 0 dynamically.
    """
    cache_key = "coe2_all_events"
    features = _events_cache.get(cache_key)
    if features is None:
        layer_url = await _coe2_layer_url()
        data = await _get_json(
            f"{layer_url}/query",
            params={
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "false",
                "f": "json",
            },
        )
        features = data.get("features") or []
        _events_cache.set(cache_key, features)

    q = _strip(query)
    p = _strip(provincia)
    c = _strip(canton)
    e = _strip(evento)
    st = _strip(estado)

    matched: list[dict[str, Any]] = []
    for feat in features:
        attrs = feat.get("attributes") or {}
        blob = _strip(
            " ".join(
                str(attrs.get(k, ""))
                for k in (
                    "Provincia",
                    "Canton",
                    "Parroquia",
                    "Sector",
                    "Evento",
                    "Causa",
                    "CategoriaDelEvento",
                    "DescripcionGeneralDeEvento",
                    "EstadoDelEvento",
                    "Region",
                )
            )
        )
        if p and p not in _strip(str(attrs.get("Provincia", ""))):
            continue
        if c and c not in _strip(str(attrs.get("Canton", ""))):
            continue
        if e and e not in _strip(str(attrs.get("Evento", ""))):
            continue
        if st and st not in _strip(str(attrs.get("EstadoDelEvento", ""))):
            continue
        if q and q not in blob:
            continue
        matched.append(attrs)

    # Prefer active/follow-up events first
    def sort_key(item: dict[str, Any]) -> tuple:
        estado_val = _strip(str(item.get("EstadoDelEvento", "")))
        active = 0 if "seguimiento" in estado_val else 1
        return (active, str(item.get("FechaDelEvento", "")), str(item.get("OBJECTID", 0)))

    matched.sort(key=sort_key)
    limit = min(max(limit, 1), 100)
    return {
        "total": len(matched),
        "source": "SGR COE2 MapServer",
        "events": matched[:limit],
    }


async def list_sat_stations(limit: int = 50) -> dict[str, Any]:
    """List tsunami early-warning SAT station points."""
    data = await _get_json(
        f"{_SAT_LAYER}/query",
        params={
            "where": "1=1",
            "outFields": "Name,FolderPath,FID",
            "returnGeometry": "true",
            "f": "json",
        },
    )
    features = data.get("features") or []
    stations = []
    for feat in features[: max(limit, 1)]:
        attrs = feat.get("attributes") or {}
        geom = feat.get("geometry") or {}
        stations.append(
            {
                "name": attrs.get("Name"),
                "folder": attrs.get("FolderPath"),
                "lon": geom.get("x"),
                "lat": geom.get("y"),
            }
        )
    return {
        "total": len(features),
        "source": "SGR SAT MapServer",
        "stations": stations,
    }

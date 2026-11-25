"""Client for the Ministry of Environment's spatial data infrastructure (GeoServer WFS).

The Ministerio de Ambiente y Energía (formerly MAATE) serves its environmental
layers from an open GeoServer at `ide.ambiente.gob.ec:8080/geoserver`, found
through the `config.js` of its interactive map
(`http://ide.ambiente.gob.ec/mapainteractivo/`, an nfms4redd portal) and
confirmed live 2026-11-24, no login. WFS 2.0.0 GetCapabilities lists 94
feature types: 93 in the ministry's `mae_ide` workspace and GeoServer's own
`tiger` demo layer, which is left out. They include:

- land cover (`v_ff010_cobertura_vegetal_<año>_a`) for 1990, 2000, 2008, 2014,
  2016, 2018, 2020, 2022 and 2024;
- deforestation by period (`v_fc010_deforestacion_<desde>_<hasta>_a`),
  1990-2024;
- the protected-area system (`v_fa210_snap_a`, 81 areas, and a Galápagos
  layer), protective forests and vegetation, carbon by forest stratum,
  ecosystems, protected springs, and mining contamination 2009-2023.

The service answers over plain HTTP on port 8080 only; the HTTPS host does not
answer. Polygon layers are large (2024 land cover has 290,004 features), so
feature samples never carry geometry: DescribeFeatureType names the
attributes and GetFeature asks only for the non-geometry ones (`propertyName`).
Same discovery-plus-sample scope as helpers/igm_client.py; the GetCapabilities
catalog is cached on disk and served stale when the host is down.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_PORTAL = "http://ide.ambiente.gob.ec/mapainteractivo/"
_WFS_URL = "http://ide.ambiente.gob.ec:8080/geoserver/ows"
# GeoServer ships a demo workspace; it is not the ministry's data.
_EXCLUDED_WORKSPACES = ("tiger:",)

MAX_FEATURE_COUNT = 20
_DEFAULT_FEATURE_COUNT = 5

_catalog_cache = TtlCache(ttl_seconds=43200.0, max_entries=1, persist="maate_catalogo")
_fetch_lock = asyncio.Lock()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feature_types(xml_bytes: bytes) -> list[dict[str, Any]]:
    """WFS 2.0 GetCapabilities → catalog entries, the demo workspace dropped."""
    root = ET.fromstring(xml_bytes)
    entries = []
    for feature_type in root.iter():
        if _local(feature_type.tag) != "FeatureType":
            continue
        fields: dict[str, Any] = {}
        bbox = None
        for child in feature_type:
            tag = _local(child.tag)
            if tag in ("Name", "Title", "Abstract") and child.text:
                fields[tag] = child.text.strip()
            elif tag == "WGS84BoundingBox":
                corners = {
                    _local(c.tag): [float(v) for v in (c.text or "").split()] for c in child
                }
                lower, upper = corners.get("LowerCorner"), corners.get("UpperCorner")
                if lower and upper and len(lower) == 2 and len(upper) == 2:
                    bbox = {"minx": lower[0], "miny": lower[1], "maxx": upper[0], "maxy": upper[1]}
        name = fields.get("Name")
        if not name or name.startswith(_EXCLUDED_WORKSPACES):
            continue
        entries.append(
            {
                "name": name,
                "title": fields.get("Title") or name,
                "abstract": fields.get("Abstract") or None,
                "bbox_geografico": bbox,
                "wfs_disponible": True,
            }
        )
    return entries


async def _fetch_catalog_fresh() -> list[dict[str, Any]]:
    cached = _catalog_cache.get("catalog")
    if cached is not None:
        return cached
    async with _fetch_lock:
        cached = _catalog_cache.get("catalog")
        if cached is not None:
            return cached
        url = f"{_WFS_URL}?" + urlencode(
            {"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"}
        )
        logger.info("Descargando GetCapabilities WFS del Ministerio de Ambiente")
        raw, truncated = await download_bytes(url)
        if truncated:
            raise ValueError("El GetCapabilities WFS del Ministerio de Ambiente superó el límite de descarga.")
        catalog = sorted(parse_feature_types(raw), key=lambda e: e["name"])
        if catalog:
            _catalog_cache.set("catalog", catalog)
        return catalog


async def _fetch_catalog() -> list[dict[str, Any]]:
    """Fresh fetch, or the last good copy when the source fails (see TtlCache.serve_stale)."""
    try:
        return await _fetch_catalog_fresh()
    except Exception as exc:
        stale = _catalog_cache.serve_stale("catalog", exc)
        if stale is None:
            raise
        return stale


async def search_capas(query: str = "") -> dict[str, Any]:
    """List layers matching ``query`` (name, title, abstract; accent-insensitive).

    Every word of the query must appear somewhere in the layer's name, title or
    abstract, so "deforestacion 22" finds ``v_fc010_deforestacion_22_24_a``
    (names use underscores, so the whole phrase would never be a substring).
    """
    catalog = await _fetch_catalog()
    words = _strip(query).split()
    matched = [
        e
        for e in catalog
        if all(
            word in _strip(f"{e['name']} {e['title']} {e['abstract'] or ''}") for word in words
        )
    ]
    return {
        "total": len(matched),
        "total_en_catalogo": len(catalog),
        "total_con_wfs": len(catalog),
        "source": "Ministerio de Ambiente y Energía — IDE (GeoServer WFS)",
        "url_fuente": _PORTAL,
        "capas": matched,
    }


def _exception_text(raw: bytes) -> str:
    message = raw.decode("utf-8", errors="replace")[:300]
    try:
        root = ET.fromstring(raw)
        text = next(
            (el.text for el in root.iter() if _local(el.tag) == "ExceptionText" and el.text), None
        )
        return text.strip() if text else message
    except ET.ParseError:
        return message


async def _get_json(url: str, what: str) -> dict[str, Any]:
    raw, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(
            f"La respuesta {what} del Ministerio de Ambiente superó el límite de descarga; reduce count."
        )
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        # GeoServer reports errors as an XML ows:ExceptionReport even when JSON was asked for.
        raise ValueError(f"{what} falló: {_exception_text(raw)}") from exc


async def get_layer_features(
    layer_name: str, count: int = _DEFAULT_FEATURE_COUNT
) -> dict[str, Any]:
    """A bounded sample of a layer's attributes (no geometry), via WFS GetFeature."""
    catalog = await _fetch_catalog()
    entry = next((e for e in catalog if e["name"] == layer_name), None)
    if entry is None:
        raise ValueError(
            f"Capa '{layer_name}' no encontrada en el catálogo del Ministerio de Ambiente. "
            "Usa search_capas_geo(fuente='maate') para ver los nombres (con su prefijo mae_ide:)."
        )
    describe = await _get_json(
        f"{_WFS_URL}?"
        + urlencode(
            {
                "service": "WFS",
                "version": "2.0.0",
                "request": "DescribeFeatureType",
                "typeNames": layer_name,
                "outputFormat": "application/json",
            }
        ),
        "DescribeFeatureType",
    )
    props = ((describe.get("featureTypes") or [{}])[0]).get("properties") or []
    geometry = next((p for p in props if str(p.get("type", "")).startswith("gml:")), None)
    campos = [p["name"] for p in props if p is not geometry and p.get("name")]

    capped = max(1, min(count, MAX_FEATURE_COUNT))
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": layer_name,
        "count": capped,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }
    if campos:
        params["propertyName"] = ",".join(campos)
    url = f"{_WFS_URL}?" + urlencode(params)
    logger.info(
        "Consultando GetFeature del Ministerio de Ambiente para la capa %s (count=%d)",
        layer_name,
        capped,
    )
    payload = await _get_json(url, "GetFeature")

    tipo = geometry.get("localType") if geometry else None
    features = [
        {"id": f.get("id"), "tipo_geometria": tipo, "propiedades": f.get("properties") or {}}
        for f in payload.get("features") or []
    ]
    return {
        "capa": layer_name,
        "titulo": entry["title"],
        "tipo_geometria": tipo,
        "campos": campos,
        "total_features_en_capa": payload.get("numberMatched") or payload.get("totalFeatures"),
        "features_devueltas": len(features),
        "features": features,
        "nota": (
            "Solo atributos: la geometría se omite (las capas de cobertura y deforestación "
            "tienen cientos de miles de polígonos). Para la geometría usa el WFS directamente "
            "con outputFormat=application/json o SHAPE-ZIP. El servicio responde solo por HTTP, "
            "puerto 8080."
        ),
        "url_consulta": url,
    }

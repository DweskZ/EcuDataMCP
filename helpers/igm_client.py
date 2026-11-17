"""Client for the Instituto Geográfico Militar's geoportal (GeoServer WFS).

`www.geoportaligm.gob.ec` serves Ecuador's official base cartography as open
WFS 2.0 (confirmed live 2026-11-04 and 2026-11-07, no login):

- `/nacional/wfs`: 68 layers, 1:1,000,000 national cartography 2024
  (`nacional_2024`: boundaries, settlements, roads, rivers, contours, EEZ...)
  plus older `igm` layers.
- `/50k/wfs`: 629 layers at 1:50,000 (`actualizada`, `galapagos50k`, `igm`)
  and 124 in `igm_reservada`, which answer 401 and are left out.
- `/25k/wfs`: 164 layers at 1:25,000 (`igm`).

Native CRS is EPSG:32717; `srsName=EPSG:4326` works. One province polygon is
about 1.5 MB, so feature samples never carry geometry: DescribeFeatureType
names the attributes, and GetFeature asks only for the non-geometry ones
(`propertyName`), which comes back with `geometry: null` and a few KB.
Same discovery-plus-sample scope as helpers/inamhi_client.py; the
GetCapabilities catalog is cached on disk and served stale when the host
is down. The free 1:1M downloads on the portal are `.rar` (excluded).
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

_BASE = "https://www.geoportaligm.gob.ec"
SERVICIOS = {
    "nacional": "Cartografía nacional 1:1.000.000 (2024)",
    "50k": "Cartografía 1:50.000",
    "25k": "Cartografía 1:25.000",
}
_RESTRICTED_WORKSPACES = ("igm_reservada:",)

MAX_FEATURE_COUNT = 20
_DEFAULT_FEATURE_COUNT = 5

_catalog_cache = TtlCache(ttl_seconds=43200.0, max_entries=1, persist="igm_catalogo")
_fetch_lock = asyncio.Lock()


def _wfs_url(servicio: str) -> str:
    return f"{_BASE}/{servicio}/wfs"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feature_types(xml_bytes: bytes, servicio: str) -> list[dict[str, Any]]:
    """WFS 2.0 GetCapabilities → catalog entries, restricted workspaces dropped."""
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
                    _local(c.tag): [float(v) for v in (c.text or "").split()]
                    for c in child
                }
                lower, upper = corners.get("LowerCorner"), corners.get("UpperCorner")
                if lower and upper and len(lower) == 2 and len(upper) == 2:
                    bbox = {"minx": lower[0], "miny": lower[1], "maxx": upper[0], "maxy": upper[1]}
        name = fields.get("Name")
        if not name or name.startswith(_RESTRICTED_WORKSPACES):
            continue
        entries.append(
            {
                "name": name,
                "title": fields.get("Title") or name,
                "abstract": fields.get("Abstract") or None,
                "servicio": servicio,
                "escala": SERVICIOS[servicio],
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
        catalog: list[dict[str, Any]] = []
        for servicio in SERVICIOS:
            url = f"{_wfs_url(servicio)}?" + urlencode(
                {"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"}
            )
            logger.info("Descargando GetCapabilities WFS del IGM (%s)", servicio)
            raw, truncated = await download_bytes(url)
            if truncated:
                raise ValueError(f"El GetCapabilities WFS del IGM ({servicio}) superó el límite de descarga.")
            catalog.extend(parse_feature_types(raw, servicio))
        catalog.sort(key=lambda e: (list(SERVICIOS).index(e["servicio"]), e["name"]))
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


async def search_capas(query: str = "", servicio: str = "") -> dict[str, Any]:
    """List IGM layers matching ``query`` (name, title, abstract; accent-insensitive).

    ``servicio`` (nacional, 50k, 25k) narrows to one scale; a word in
    ``query`` such as "50k" does not.
    """
    if servicio and servicio not in SERVICIOS:
        raise ValueError(f"servicio debe ser uno de: {', '.join(SERVICIOS)}")
    catalog = await _fetch_catalog()
    q = _strip(query)
    matched = [
        e
        for e in catalog
        if (not servicio or e["servicio"] == servicio)
        and (not q or q in _strip(e["name"]) or q in _strip(e["title"]) or q in _strip(e["abstract"]))
    ]
    return {
        "total": len(matched),
        "total_en_catalogo": len(catalog),
        "total_con_wfs": len(catalog),
        "por_servicio": {s: sum(1 for e in catalog if e["servicio"] == s) for s in SERVICIOS},
        "source": "IGM — Geoportal (GeoServer WFS)",
        "url_fuente": f"{_BASE}/portal/",
        "capas": matched,
    }


def _exception_text(raw: bytes) -> str:
    message = raw.decode("utf-8", errors="replace")[:300]
    try:
        root = ET.fromstring(raw)
        text = next((el.text for el in root.iter() if _local(el.tag) == "ExceptionText" and el.text), None)
        return text.strip() if text else message
    except ET.ParseError:
        return message


async def _get_json(url: str, what: str) -> dict[str, Any]:
    raw, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(f"La respuesta {what} del IGM superó el límite de descarga; reduce count.")
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        # GeoServer reports errors as an XML ows:ExceptionReport even when JSON was asked for.
        raise ValueError(f"{what} falló: {_exception_text(raw)}") from exc


async def get_layer_features(layer_name: str, count: int = _DEFAULT_FEATURE_COUNT) -> dict[str, Any]:
    """A bounded sample of a layer's attributes (no geometry), via WFS GetFeature."""
    catalog = await _fetch_catalog()
    entry = next((e for e in catalog if e["name"] == layer_name), None)
    if entry is None:
        if layer_name.startswith(_RESTRICTED_WORKSPACES):
            raise ValueError(f"La capa '{layer_name}' es reservada en el IGM (pide credenciales).")
        raise ValueError(
            f"Capa '{layer_name}' no encontrada en el catálogo del IGM. "
            "Usa search_capas_geo(fuente='igm') para ver los nombres (con su prefijo)."
        )
    base = _wfs_url(entry["servicio"])
    describe = await _get_json(
        f"{base}?"
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
    url = f"{base}?" + urlencode(params)
    logger.info("Consultando GetFeature del IGM para la capa %s (count=%d)", layer_name, capped)
    payload = await _get_json(url, "GetFeature")

    tipo = geometry.get("localType") if geometry else None
    features = [
        {"id": f.get("id"), "tipo_geometria": tipo, "propiedades": f.get("properties") or {}}
        for f in payload.get("features") or []
    ]
    return {
        "capa": layer_name,
        "titulo": entry["title"],
        "servicio": entry["servicio"],
        "escala": entry["escala"],
        "tipo_geometria": tipo,
        "campos": campos,
        "total_features_en_capa": payload.get("numberMatched") or payload.get("totalFeatures"),
        "features_devueltas": len(features),
        "features": features,
        "nota": (
            "Solo atributos: la geometría se omite (una provincia pesa ~1,5 MB). "
            "Para la geometría usa el WFS directamente con outputFormat=application/json "
            "o SHAPE-ZIP."
        ),
        "url_consulta": url,
    }

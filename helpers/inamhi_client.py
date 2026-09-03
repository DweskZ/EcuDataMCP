"""Client for INAMHI's geoportal (geoservicios.inamhi.gob.ec), a GeoNode-
backed GeoServer instance exposing Ecuador's meteorology/hydrology
institute's spatial layer catalog via standard OGC WMS/WFS.

Confirmed live (2026-09-02):

- WMS GetCapabilities (1.3.0, `/geoserver/wms?service=WMS&version=1.3.0&
  request=GetCapabilities`) returns 222 layers, all in a single `geonode`
  workspace: monthly + annual precipitation climate normals for
  1985-2015 (`enero1985_2015` .. `diciembre1985_2015`, `anual_1985_2015_r`),
  ~180 dated daily rainfall-anomaly composites (`anomalias_DDmonYYYY`),
  WRF numerical weather model output grids (`wrf_tiempo_precipitacion`,
  `_temperatura`, `_temperatura_calibrada`, `_humedad`, `_presion`,
  `_viento`), administrative/hydrographic boundaries (`provincias`,
  `ecuador_cantones`, `ecuador_parroquias`, `cuencas_inamhi`,
  `cuencas_maate`, `demarcaciones_hidrograficas`), and a handful of named
  regional layers (`amazonia`, `sierra`, `galapagos`, `costa_dis`,
  `costa_provincias`, `hidroelectricasshape`, `geoglows_ecuador`,
  `regiones_precip`, `regiones_tempe`, `zonas_modelo_cuenca_esmeraldas`,
  three `u75/u90/u95_el_coca` percentile rasters). Titles/abstracts are
  populated for only a few layers (e.g. `ecuador_cantones`); most layers
  have no Abstract and a Title identical to their Name.
- WFS GetCapabilities (2.0.0, same host/`wfs` endpoint) lists 199 of those
  222 as real feature types -- every layer except 23 pure-raster ones (the
  13 precipitation climate-normal grids, the 6 `wrf_tiempo_*` weather-model
  grids, and 3 `u75/u90/u95_el_coca` percentile rasters), which are
  WMS-only (confirmed: WFS GetFeature on `wrf_tiempo_precipitacion`
  returns an `InvalidParameterValue`/"Feature type unknown" exception).
  GetFeature confirmed live to return real, non-empty attribute data for
  vector layers -- e.g. `regiones_precip` returns per-polygon zonal
  precipitation stats (`rango`, `dhnom` demarcación name, `area_km2`),
  `anomalias_01aug2016` returns per-polygon anomaly `min/max/mean/sum`,
  `cuencas_inamhi` returns named watershed polygons. `outputFormat=
  application/json` works and is used here instead of parsing GML.
- NOT found anywhere in the 222 layers: a point-feature "estaciones
  meteorológicas/hidrológicas" layer with per-station raw daily/hourly
  observations (precipitación, temperatura, caudal by station). Everything
  exposed via WFS is a polygon-aggregated product (zonal anomaly/
  climate-normal statistics, watershed/administrative boundaries) -- useful
  for spatial analysis, not a substitute for a raw station time series. If
  INAMHI adds a stations layer later, `search_inamhi_capas` surfaces it via
  name/title match without any code change here.
- TLS: plain httpx (via helpers.csv_reader.download_bytes) verifies cleanly
  against this host with certifi's default CA bundle -- confirmed live, no
  helpers.tls fallback needed. (A local `curl` invocation on Windows failed
  with schannel's CRYPT_E_NO_REVOCATION_CHECK; that is a curl/schannel
  revocation-check artifact, not a real certificate-chain problem, and does
  not reproduce under httpx/OpenSSL.)
- No CKAN organization for INAMHI exists anywhere in this codebase's CKAN
  coverage (datosabiertos.gob.ec et al.) -- this GeoServer is the only
  automatable path to INAMHI's published data today, so this client adds
  coverage rather than duplicating an existing CKAN org.

Scope: catalog layers (name, title, abstract, CRS list, geographic bounding
box, WFS availability) from GetCapabilities, plus one bounded GetFeature
call per layer for callers that want to sample a vector layer's actual
attributes. This is deliberately not a spatial query engine: no bbox/CQL
filtering, no reprojection, no raster pixel access -- just discovery plus a
capped sample, matching the "easy" scope this integration was picked for.
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

_GEOSERVER_BASE = "https://geoservicios.inamhi.gob.ec/geoserver"
_WMS_URL = f"{_GEOSERVER_BASE}/wms"
_WFS_URL = f"{_GEOSERVER_BASE}/wfs"

_WMS_NS = {"wms": "http://www.opengis.net/wms"}

# A spot-check sample of a layer's own attributes, not a bulk extraction
# tool -- same "small, bounded preview" rationale as preview_resource_data's
# row cap.
MAX_FEATURE_COUNT = 20
_DEFAULT_FEATURE_COUNT = 5

# The capabilities catalog is confirmed to change rarely (INAMHI appends a
# handful of new dated `anomalias_*` layers over time, nothing structurally
# dynamic) -- several hours balances staleness against re-fetching and
# re-parsing a ~1 MB WMS + ~0.5 MB WFS XML document on every call.
_catalog_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()


def _local(tag: str) -> str:
    """Strip a `{namespace}tag` qualified name down to its local part."""
    return tag.rsplit("}", 1)[-1]


def _parse_wms_layers(xml_bytes: bytes) -> dict[str, dict[str, Any]]:
    """Parse WMS GetCapabilities XML into {layer_name: catalog entry}."""
    root = ET.fromstring(xml_bytes)
    capability = root.find("wms:Capability", _WMS_NS)
    if capability is None:
        return {}
    top_layer = capability.find("wms:Layer", _WMS_NS)
    if top_layer is None:
        return {}

    layers: dict[str, dict[str, Any]] = {}
    for layer_el in top_layer.findall("wms:Layer", _WMS_NS):
        name_el = layer_el.find("wms:Name", _WMS_NS)
        if name_el is None or not (name_el.text and name_el.text.strip()):
            continue
        name = name_el.text.strip()

        title_el = layer_el.find("wms:Title", _WMS_NS)
        title = title_el.text.strip() if title_el is not None and title_el.text else name

        abstract_el = layer_el.find("wms:Abstract", _WMS_NS)
        abstract = (
            abstract_el.text.strip() if abstract_el is not None and abstract_el.text else None
        )

        crs_list = sorted(
            {c.text.strip() for c in layer_el.findall("wms:CRS", _WMS_NS) if c.text}
        )

        bbox_el = layer_el.find("wms:EX_GeographicBoundingBox", _WMS_NS)
        bbox = None
        if bbox_el is not None:
            bbox = {
                _local(child.tag): float(child.text)
                for child in bbox_el
                if child.text is not None
            }

        layers[name] = {
            "name": name,
            "title": title,
            "abstract": abstract,
            "crs": crs_list,
            "bbox_geografico": bbox,
            "wfs_disponible": False,  # filled in by _fetch_catalog once WFS is parsed
        }
    return layers


def _parse_wfs_type_names(xml_bytes: bytes) -> set[str]:
    """Parse WFS GetCapabilities XML into the set of available feature type names."""
    root = ET.fromstring(xml_bytes)
    feature_type_list = None
    for child in root:
        if _local(child.tag) == "FeatureTypeList":
            feature_type_list = child
            break
    if feature_type_list is None:
        return set()

    names: set[str] = set()
    for feature_type in feature_type_list:
        if _local(feature_type.tag) != "FeatureType":
            continue
        for child in feature_type:
            if _local(child.tag) == "Name" and child.text:
                names.add(child.text.strip())
                break
    return names


async def _fetch_catalog() -> list[dict[str, Any]]:
    cached = _catalog_cache.get("catalog")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _catalog_cache.get("catalog")
        if cached is not None:
            return cached

        logger.info("Descargando GetCapabilities de WMS/WFS del geoportal de INAMHI")
        wms_url = f"{_WMS_URL}?" + urlencode(
            {"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"}
        )
        wfs_url = f"{_WFS_URL}?" + urlencode(
            {"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"}
        )

        wms_bytes, wms_truncated = await download_bytes(wms_url)
        if wms_truncated:
            raise ValueError(
                "El documento GetCapabilities de WMS de INAMHI superó el límite de descarga."
            )
        wfs_bytes, wfs_truncated = await download_bytes(wfs_url)
        if wfs_truncated:
            raise ValueError(
                "El documento GetCapabilities de WFS de INAMHI superó el límite de descarga."
            )

        layers = _parse_wms_layers(wms_bytes)
        wfs_names = _parse_wfs_type_names(wfs_bytes)
        for name, entry in layers.items():
            entry["wfs_disponible"] = name in wfs_names

        catalog = sorted(layers.values(), key=lambda entry: entry["name"])
        if catalog:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/bce_remesas_client.py / helpers/contraloria_client.py.
            _catalog_cache.set("catalog", catalog)
        return catalog


async def search_capas(query: str = "", solo_wfs: bool = False) -> dict[str, Any]:
    """
    List (optionally filtered) layers from INAMHI's geoportal (GeoServer WMS/WFS
    capabilities).

    Args:
        query: Free text matched (accent-insensitive) against the layer's
            name, title, or abstract. Empty returns all layers.
        solo_wfs: If True, only return layers with WFS (real attribute/
            feature data) available -- excludes the pure-raster layers.
    """
    catalog = await _fetch_catalog()
    q = _strip(query)
    matched = [
        entry
        for entry in catalog
        if (not q or q in _strip(entry["name"]) or q in _strip(entry["title"]) or q in _strip(entry["abstract"]))
        and (not solo_wfs or entry["wfs_disponible"])
    ]
    return {
        "total": len(matched),
        "total_en_catalogo": len(catalog),
        "total_con_wfs": sum(1 for entry in catalog if entry["wfs_disponible"]),
        "source": "INAMHI — Geoportal (GeoServer WMS/WFS)",
        "url_wms_capabilities": f"{_WMS_URL}?service=WMS&version=1.3.0&request=GetCapabilities",
        "url_wfs_capabilities": f"{_WFS_URL}?service=WFS&version=2.0.0&request=GetCapabilities",
        "capas": matched,
    }


async def get_layer_features(layer_name: str, count: int = _DEFAULT_FEATURE_COUNT) -> dict[str, Any]:
    """
    Fetch a small, bounded sample of a layer's real feature attributes via WFS
    GetFeature (JSON output) -- confirms and previews what a vector layer
    actually contains, not a general spatial query engine (no bbox/CQL
    filtering).

    Args:
        layer_name: Layer name as returned by search_capas, e.g.
            "geonode:regiones_precip" (the "geonode:" workspace prefix is
            required by GeoServer's WFS -- pass it as returned, don't strip it).
        count: Number of features to fetch (1-20, default 5). Capped to keep
            the response small -- this is a sample, not a bulk export.
    """
    catalog = await _fetch_catalog()
    entry = next((e for e in catalog if e["name"] == layer_name), None)
    if entry is None:
        raise ValueError(
            f"Capa '{layer_name}' no encontrada en el catálogo de INAMHI. "
            "Usa search_inamhi_capas para ver los nombres disponibles."
        )
    if not entry["wfs_disponible"]:
        raise ValueError(
            f"La capa '{layer_name}' es solo WMS (ráster) -- no tiene datos "
            "de atributos vía WFS. Solo se puede consultar como mapa/imagen "
            "(GetMap), no como datos tabulares."
        )

    capped_count = max(1, min(count, MAX_FEATURE_COUNT))
    url = f"{_WFS_URL}?" + urlencode(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": layer_name,
            "count": capped_count,
            "outputFormat": "application/json",
        }
    )
    logger.info("Consultando GetFeature de INAMHI para la capa %s (count=%d)", layer_name, capped_count)
    raw, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(
            f"La respuesta GetFeature de '{layer_name}' superó el límite de descarga; "
            "reduce el parámetro count."
        )

    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        # GeoServer reports errors (even for outputFormat=json requests) as
        # an XML ows:ExceptionReport, not JSON.
        message = raw.decode("utf-8", errors="replace")
        try:
            error_root = ET.fromstring(raw)
            text_el = next(
                (el for el in error_root.iter() if _local(el.tag) == "ExceptionText"), None
            )
            if text_el is not None and text_el.text:
                message = text_el.text.strip()
        except ET.ParseError:
            pass
        raise ValueError(f"GetFeature falló para '{layer_name}': {message}") from exc

    features = payload.get("features") or []
    # Geometry coordinate arrays can be tens of KB per feature (matches the
    # WKT/geometry-stripping rationale in helpers/csv_reader.py) -- keep only
    # the geometry type, drop the coordinates, and surface attributes.
    atributos = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        atributos.append(
            {
                "id": feature.get("id"),
                "tipo_geometria": geometry.get("type"),
                "propiedades": feature.get("properties") or {},
            }
        )

    return {
        "capa": layer_name,
        "titulo": entry["title"],
        "total_features_en_capa": payload.get("totalFeatures") or payload.get("numberMatched"),
        "features_devueltas": len(atributos),
        "features": atributos,
        "url_consulta": url,
    }

"""Client for the Ministry of Agriculture's geoportal (geoportal.agricultura.gob.ec,
"Geoportal del Agro Ecuatoriano" / SIPA), a GeoServer instance exposing
Ecuador's agriculture spatial layer catalog via standard OGC WMS/WFS -- same
family of source as helpers/inamhi_client.py, but structurally different
enough (no single root GetCapabilities, WMS/WFS layer names disagree) to
need its own endpoint discovery and name-matching logic.

Confirmed live (2026-09-03):

- Protocol gap re-confirmed directly (not assumed from prior notes): only
  `http://` loads. `https://` fails at the TLS handshake itself (a plain
  `ConnectError`/"SSL/TLS connection failed" -- the port doesn't complete a
  handshake, this is not a certificate-trust issue `helpers.tls`'s fallback
  paths would fix).
- Unlike INAMHI, there is no site-wide `/geoserver/wms` reverse-proxy path
  on this host -- `/geoserver/wms`, `/geoserver/web/`, `/geoserver/<any
  workspace>/wms` all return a genuine Apache "Not Found" (Apache/CentOS
  error page, no GeoServer/Tomcat signature at all), confirmed against every
  workspace name listed in prior research plus several ports (8080/8081/
  8443) and OWS-style URLs. The real GeoServer is instead reverse-proxied
  per "virtual workspace" at root-relative paths -- discovered by reading
  the *official* map viewer's own config at
  `/geovisor/config/dataconfig.js` (the page embeds this viewer in an
  iframe from its homepage), which hardcodes every `url: "/<categoria>/
  <store>/wms"` the real site itself calls. That gives 24 confirmed-live
  (categoria, store) endpoint pairs across 8 categories -- `registros`
  (E50k, E5k), `demarcacion` (E250k, E25k, E50k, E5k, zonificacion_pastos),
  `infraestructura` (E50k), `tematicas` (E25k, E50k, Rraster), `cobertura`
  (E100k, E25k, E25k_asociacion_objetos, E5k), `fisiografia` (E25k,
  Rraster), `sigtierras` (catastro_rural, cobertura_tierra, geomorfologia,
  geopedologia, zonificaciones), `agroestadistica` (riesgos_agroclimaticos,
  tipologias_territorio_hih). A 25th pair from the same config,
  `geosigtierras/accesibilidad`, times out live (confirmed, excluded here).
  A 26th URL in that config (`http://geoportal.sigtierras.gob.ec:8080/
  geoserver/sigtierras/wms`) is a *different* host entirely -- out of scope
  for this client, which stays scoped to geoportal.agricultura.gob.ec.
- 277 WMS layers confirmed live across those 24 endpoints. 257 also expose
  real WFS GetFeature data. The 20 WMS-only layers are concentrated in 4
  stores: `tematicas/Rraster` (2, pure raster coverages), `fisiografia/
  Rraster` (3, pure raster coverages), `sigtierras/catastro_rural` (8 --
  WFS explicitly disabled server-side, confirmed via GeoServer's own
  ows:ExceptionReport: "Service WFS is disabled" -- despite this being the
  rural cadastre store flagged as most valuable by prior research;
  `catastro_rural_junio_2023`/`predios`/`construcciones` are map-only here),
  and `agroestadistica/tipologias_territorio_hih` (7, same "Service WFS is
  disabled" exception). `agroestadistica/riesgos_agroclimaticos` (52
  layers, agroclimatic risk data as prior research flagged) *does* have WFS
  enabled and confirmed working.
- GOTCHA (specific to this source, INAMHI didn't have this): a layer's WMS
  `<Name>` is unprefixed (e.g. "vw_censo_palmicultor"), but the same
  layer's WFS `<FeatureType><Name>` is prefixed with the *store* name, not
  the categoria (e.g. "E50k:vw_censo_palmicultor") -- confirmed live for
  `registros/E50k`. This client matches WMS<->WFS entries by comparing the
  bare name (stripping any "prefix:") and separately records the
  WFS-qualified name as the one required for GetFeature's `typeNames`.
- GetFeature confirmed live to return large amounts of real, rich attribute
  data, not a gated/empty response -- e.g. `demarcacion/E25k`'s
  "E25k:vw_hg000_zae_cafe_arabigo" (zonificación agroecológica) returned
  totalFeatures=724971 with 20+ real per-polygon attributes (provincia,
  cantón, categoría de zonificación agroecológica, pendiente, textura,
  drenaje, fertilidad, etc.), and `agroestadistica/riesgos_agroclimaticos`
  exposes real named multi-risk layers (e.g.
  "riesgos_agroclimaticos:vw_02c3_multiriesgo_forestal").
- No root/site-wide GetCapabilities exists here (unlike INAMHI's single
  `geonode` workspace) -- this client fetches WMS+WFS GetCapabilities for
  each of the 24 known endpoint pairs (concurrently, bounded) and merges
  them into one catalog. The endpoint list is hardcoded from the viewer's
  own config rather than discovered dynamically, since there is no
  enumeration endpoint for the (categoria, store) pairs themselves.

Scope: same as helpers/inamhi_client.py -- catalog discovery (name, title,
abstract, CRS list, geographic bounding box, WFS availability) from
GetCapabilities, plus one bounded GetFeature call per layer for callers
that want to sample a vector layer's actual attributes. Not a spatial query
engine: no bbox/CQL filtering, no reprojection, no raster pixel access.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import httpx

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE_URL = "http://geoportal.agricultura.gob.ec"

_WMS_NS = {"wms": "http://www.opengis.net/wms"}

# (categoria, store) pairs -- read live from the official viewer's own
# config (/geovisor/config/dataconfig.js), not discovered dynamically; see
# module docstring. Excludes geosigtierras/accesibilidad (times out live)
# and the sigtierras workspace hosted on the *different* geoportal.
# sigtierras.gob.ec:8080 domain (out of scope for this client).
_ENDPOINTS: list[tuple[str, str]] = [
    ("registros", "E50k"),
    ("registros", "E5k"),
    ("demarcacion", "E250k"),
    ("demarcacion", "E25k"),
    ("demarcacion", "E50k"),
    ("demarcacion", "E5k"),
    ("demarcacion", "zonificacion_pastos"),
    ("infraestructura", "E50k"),
    ("tematicas", "E25k"),
    ("tematicas", "E50k"),
    ("tematicas", "Rraster"),
    ("cobertura", "E100k"),
    ("cobertura", "E25k"),
    ("cobertura", "E25k_asociacion_objetos"),
    ("cobertura", "E5k"),
    ("fisiografia", "E25k"),
    ("fisiografia", "Rraster"),
    ("sigtierras", "catastro_rural"),
    ("sigtierras", "cobertura_tierra"),
    ("sigtierras", "geomorfologia"),
    ("sigtierras", "geopedologia"),
    ("sigtierras", "zonificaciones"),
    ("agroestadistica", "riesgos_agroclimaticos"),
    ("agroestadistica", "tipologias_territorio_hih"),
]

# Don't open 48 simultaneous connections against a modest government host.
_MAX_CONCURRENT_REQUESTS = 6

# A spot-check sample of a layer's own attributes, not a bulk extraction
# tool -- same "small, bounded preview" rationale as preview_resource_data's
# row cap / helpers/inamhi_client.py's MAX_FEATURE_COUNT.
MAX_FEATURE_COUNT = 20
_DEFAULT_FEATURE_COUNT = 5

# The catalog spans 24 GetCapabilities documents (48 requests) -- confirmed
# to be a slow-changing cadastral/thematic layer catalog, not a live-data
# feed, so a long TTL trades staleness for not re-fetching/re-parsing that
# on every call.
_catalog_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()


def _local(tag: str) -> str:
    """Strip a `{namespace}tag` qualified name down to its local part."""
    return tag.rsplit("}", 1)[-1]


def _bare_name(name: str) -> str:
    """Strip a GeoServer `workspace:name` qualifier down to the bare name."""
    return name.rsplit(":", 1)[-1]


def _parse_wms_layers(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Parse one WMS GetCapabilities document into a list of layer entries."""
    root = ET.fromstring(xml_bytes)
    capability = root.find("wms:Capability", _WMS_NS)
    if capability is None:
        return []
    top_layer = capability.find("wms:Layer", _WMS_NS)
    if top_layer is None:
        return []

    layers: list[dict[str, Any]] = []
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

        layers.append(
            {
                "name": name,
                "title": title,
                "abstract": abstract,
                "crs": crs_list,
                "bbox_geografico": bbox,
            }
        )
    return layers


def _parse_wfs_type_names(xml_bytes: bytes) -> dict[str, str]:
    """Parse a WFS GetCapabilities document into {bare_name: qualified_name}.

    Returns an empty dict both when WFS is disabled for this endpoint
    (GeoServer replies with an ows:ExceptionReport -- confirmed live for
    sigtierras/catastro_rural and agroestadistica/tipologias_territorio_hih)
    and when it's enabled but the store has no vector feature types (pure
    raster stores, e.g. */Rraster) -- both cases mean "no WFS data here",
    which is all the caller needs to know.
    """
    root = ET.fromstring(xml_bytes)
    feature_type_list = None
    for child in root:
        if _local(child.tag) == "FeatureTypeList":
            feature_type_list = child
            break
    if feature_type_list is None:
        return {}

    names: dict[str, str] = {}
    for feature_type in feature_type_list:
        if _local(feature_type.tag) != "FeatureType":
            continue
        for child in feature_type:
            if _local(child.tag) == "Name" and child.text:
                qualified = child.text.strip()
                names[_bare_name(qualified)] = qualified
                break
    return names


async def _fetch_endpoint(
    session: httpx.AsyncClient, semaphore: asyncio.Semaphore, categoria: str, store: str
) -> list[dict[str, Any]]:
    """Fetch + merge WMS/WFS capabilities for one (categoria, store) pair.

    Failures are per-endpoint, not fatal to the whole catalog fetch -- one
    broken store (e.g. a future geosigtierras/accesibilidad-style timeout)
    shouldn't take down the other 23.
    """
    wms_url = f"{_BASE_URL}/{categoria}/{store}/wms?" + urlencode(
        {"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"}
    )
    wfs_url = f"{_BASE_URL}/{categoria}/{store}/wfs?" + urlencode(
        {"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"}
    )
    try:
        async with semaphore:
            wms_bytes, wms_truncated = await download_bytes(wms_url, session=session)
        if wms_truncated:
            logger.warning("GetCapabilities de WMS truncado para %s/%s, se omite", categoria, store)
            return []
        wms_layers = _parse_wms_layers(wms_bytes)
        if not wms_layers:
            return []

        async with semaphore:
            wfs_bytes, wfs_truncated = await download_bytes(wfs_url, session=session)
        wfs_by_bare = {} if wfs_truncated else _parse_wfs_type_names(wfs_bytes)
    except Exception:
        logger.warning("No se pudo consultar el endpoint %s/%s del geoportal MAG", categoria, store, exc_info=True)
        return []

    entries = []
    for layer in wms_layers:
        wfs_typename = wfs_by_bare.get(layer["name"])
        entries.append(
            {
                "id": f"{categoria}/{store}/{layer['name']}",
                "categoria": categoria,
                "store": store,
                "name": layer["name"],
                "title": layer["title"],
                "abstract": layer["abstract"],
                "crs": layer["crs"],
                "bbox_geografico": layer["bbox_geografico"],
                "wfs_disponible": wfs_typename is not None,
                "wfs_typename": wfs_typename,
            }
        )
    return entries


async def _fetch_catalog() -> list[dict[str, Any]]:
    cached = _catalog_cache.get("catalog")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _catalog_cache.get("catalog")
        if cached is not None:
            return cached

        logger.info(
            "Descargando GetCapabilities de WMS/WFS del geoportal del MAG (%d endpoints)",
            len(_ENDPOINTS),
        )
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
        async with httpx.AsyncClient(headers={"User-Agent": "EcuDataMCP/1.0"}) as session:
            results = await asyncio.gather(
                *(
                    _fetch_endpoint(session, semaphore, categoria, store)
                    for categoria, store in _ENDPOINTS
                )
            )

        catalog = sorted(
            (entry for endpoint_entries in results for entry in endpoint_entries),
            key=lambda entry: entry["id"],
        )
        if catalog:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/inamhi_client.py / helpers/bce_remesas_client.py.
            _catalog_cache.set("catalog", catalog)
        return catalog


async def search_capas(query: str = "", solo_wfs: bool = False, categoria: str = "") -> dict[str, Any]:
    """
    List (optionally filtered) layers from the Ministry of Agriculture's
    geoportal (geoportal.agricultura.gob.ec, GeoServer WMS/WFS).

    Args:
        query: Free text matched (accent-insensitive) against the layer's
            id, name, title, or abstract. Empty returns all layers.
        solo_wfs: If True, only return layers with WFS (real attribute/
            feature data) available -- excludes raster-only and
            WFS-disabled stores.
        categoria: Optional exact (case/accent-insensitive) filter on one of
            the 8 top-level categories: registros, demarcacion,
            infraestructura, tematicas, cobertura, fisiografia, sigtierras,
            agroestadistica. Empty returns all categories.
    """
    catalog = await _fetch_catalog()
    q = _strip(query)
    cat_filter = _strip(categoria)
    matched = [
        entry
        for entry in catalog
        if (
            not q
            or q in _strip(entry["id"])
            or q in _strip(entry["name"])
            or q in _strip(entry["title"])
            or q in _strip(entry["abstract"])
        )
        and (not solo_wfs or entry["wfs_disponible"])
        and (not cat_filter or _strip(entry["categoria"]) == cat_filter)
    ]
    return {
        "total": len(matched),
        "total_en_catalogo": len(catalog),
        "total_con_wfs": sum(1 for entry in catalog if entry["wfs_disponible"]),
        "categorias": sorted({entry["categoria"] for entry in catalog}),
        "source": "Ministerio de Agricultura y Ganadería — Geoportal del Agro Ecuatoriano (GeoServer WMS/WFS)",
        "capas": matched,
    }


async def get_layer_features(layer_id: str, count: int = _DEFAULT_FEATURE_COUNT) -> dict[str, Any]:
    """
    Fetch a small, bounded sample of a layer's real feature attributes via WFS
    GetFeature (JSON output) -- confirms and previews what a vector layer
    actually contains, not a general spatial query engine (no bbox/CQL
    filtering).

    Args:
        layer_id: Layer id as returned by search_capas, e.g.
            "demarcacion/E25k/vw_hg000_zae_cafe_arabigo" (the
            "categoria/store/name" triple, not the WFS-qualified name).
        count: Number of features to fetch (1-20, default 5). Capped to keep
            the response small -- this is a sample, not a bulk export.
    """
    catalog = await _fetch_catalog()
    entry = next((e for e in catalog if e["id"] == layer_id), None)
    if entry is None:
        raise ValueError(
            f"Capa '{layer_id}' no encontrada en el catálogo del geoportal del MAG. "
            "Usa search_sipa_geoportal_capas para ver los ids disponibles."
        )
    if not entry["wfs_disponible"]:
        raise ValueError(
            f"La capa '{layer_id}' es solo WMS (ráster o WFS deshabilitado en el "
            "servidor) -- no tiene datos de atributos vía WFS. Solo se puede "
            "consultar como mapa/imagen (GetMap), no como datos tabulares."
        )

    capped_count = max(1, min(count, MAX_FEATURE_COUNT))
    wfs_url = f"{_BASE_URL}/{entry['categoria']}/{entry['store']}/wfs?" + urlencode(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": entry["wfs_typename"],
            "count": capped_count,
            "outputFormat": "application/json",
        }
    )
    logger.info("Consultando GetFeature del geoportal MAG para %s (count=%d)", layer_id, capped_count)
    raw, truncated = await download_bytes(wfs_url)
    if truncated:
        raise ValueError(
            f"La respuesta GetFeature de '{layer_id}' superó el límite de descarga; "
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
        raise ValueError(f"GetFeature falló para '{layer_id}': {message}") from exc

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
        "capa": layer_id,
        "titulo": entry["title"],
        "total_features_en_capa": payload.get("totalFeatures") or payload.get("numberMatched"),
        "features_devueltas": len(atributos),
        "features": atributos,
        "url_consulta": wfs_url,
    }

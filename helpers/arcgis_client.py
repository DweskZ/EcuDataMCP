"""ArcGIS REST client for the electricity-sector layers of ARCONEL and CELEC,
documented in docs/RESEARCH.md § ARCONEL — servicios ArcGIS REST públicos
and § CELEC EP — sin niveles de embalse, pero ArcGIS abierto (Trigésimo
quinta pasada, re-checked 2026-10-26).

Both publish anonymous FeatureServer `/query` endpoints (maxRecordCount
2000). The layer list is curated rather than discovered:

- ARCONEL's own server (`geoportal.arconel.gob.ec:6443/.../ServDashboards`)
  holds the per-plant monthly production (219k rows) and fuel consumption,
  but it did not accept connections from a Canadian home IP on 2026-10-26
  (it did on 2026-09-29). Its Esri-cloud copies on `services3.arcgis.com`
  (org 5Gdbxgyani9QGxyU) answered: the distributor energy balance
  (1999-2024), billing/collection/subsidies/customers (1999-2025), 355
  plants, transmission lines, substations and service areas. Those are the
  ones listed here; the 6443 layers can be added once the host answers.
- CELEC's portal (`portalarcgis.celec.gob.ec/server/rest/services/Hosted`)
  lists ~55 services, most of them Survey123 forms and their `_results`
  (personal data), land parcels and orthophotos. Only the generation plants
  and the transmission network (SNT_03_2025) are listed, on purpose.

Text attributes on the ARCONEL cloud layers are double-encoded in places
("CNEL-BolÃ­var"); they are repaired when the latin-1 round trip yields
valid UTF-8. Date fields (epoch milliseconds) come back as ISO dates.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

MAX_FEATURE_COUNT = 500
_DEFAULT_FEATURE_COUNT = 5

_ARCONEL = "https://services3.arcgis.com/5Gdbxgyani9QGxyU/arcgis/rest/services"
_CELEC = "https://portalarcgis.celec.gob.ec/server/rest/services/Hosted"

_CATALOGO: dict[str, list[dict[str, str]]] = {
    "arconel": [
        {
            "capa": "balance_energia",
            "titulo": "Balance de energía por distribuidora y mes (ene 1999-abr 2024)",
            "descripcion": (
                "Energía disponible, pérdidas técnicas y no técnicas, energía facturada "
                "(regulados/no regulados) y demanda máxima, en MWh, por empresa y mes "
                "(Anio, IdMes 1-12). Los campos *MV son el total móvil de 12 meses."
            ),
            "url": f"{_ARCONEL}/resumen_balance_energia/FeatureServer/0",
        },
        {
            "capa": "facturacion",
            "titulo": "Facturación, recaudación, subsidios y clientes (1999-2025)",
            "descripcion": (
                "Por distribuidora, mes, grupo de consumo (residencial, comercial, "
                "industrial...) y tipo de cliente: clientes, MWh y USD facturados, "
                "recaudación, subsidios y consumo promedio (Anio, IdMes 1-12). Los "
                "campos *MV son el total móvil de 12 meses."
            ),
            "url": f"{_ARCONEL}/resumen_facturacion/FeatureServer/0",
        },
        {
            "capa": "centrales",
            "titulo": "Centrales de generación (355)",
            "descripcion": (
                "Empresa, tipo de central y de energía, sistema (SNI/aislado), "
                "provincia/cantón/parroquia, potencia nominal y efectiva, inicio."
            ),
            "url": f"{_ARCONEL}/CENTRALES/FeatureServer/0",
        },
        {
            "capa": "lineas_transmision",
            "titulo": "Líneas de transmisión (604)",
            "descripcion": "Empresa, subestaciones de origen/destino, voltaje, longitud, capacidad.",
            "url": f"{_ARCONEL}/LINEAS1/FeatureServer/0",
        },
        {
            "capa": "subestaciones",
            "titulo": "Subestaciones (1.381)",
            "descripcion": "Empresa, tipo, voltajes, potencia de transformación, ubicación.",
            "url": f"{_ARCONEL}/SUBESTACIONES/FeatureServer/0",
        },
        {
            "capa": "areas_servicio",
            "titulo": "Áreas de prestación del servicio eléctrico (20)",
            "descripcion": "Área de concesión de cada distribuidora (polígonos).",
            "url": (
                f"{_ARCONEL}/%C3%81reas_de_Prestaci%C3%B3n_de_Servicio_El%C3%A9ctrico"
                "/FeatureServer/0"
            ),
        },
    ],
    "celec": [
        {
            "capa": "centrales",
            "titulo": "Centrales de generación de CELEC EP (40)",
            "descripcion": (
                "Unidad de negocio, tipo de generación, capacidad instalada, potencia "
                "efectiva, unidades, nivel de tensión y códigos DPA de ubicación."
            ),
            "url": f"{_CELEC}/CENTRAL_GENERACION/FeatureServer/0",
        },
        *(
            {
                "capa": f"snt_{nombre.lower()}",
                "titulo": f"Red de transmisión SNT (marzo 2025): {titulo}",
                "descripcion": "Capa del Sistema Nacional de Transmisión de CELEC Transelectric.",
                "url": f"{_CELEC}/SNT_03_2025/FeatureServer/{layer_id}",
            }
            for layer_id, nombre, titulo in (
                (0, "ESTRUCTURA", "estructuras"),
                (5, "LINEA_TRANSMISION", "líneas de transmisión"),
                (7, "SUBESTACION", "subestaciones"),
                (8, "ZONA_OPERATIVA", "zonas operativas"),
            )
        ),
    ],
}

_SOURCES = {
    "arconel": "ARCONEL — servicios ArcGIS del SISDAT (services3.arcgis.com)",
    "celec": "CELEC EP — portal ArcGIS (portalarcgis.celec.gob.ec)",
}

# Layer metadata (fields, geometry type) only changes with a republish.
_meta_cache = TtlCache(ttl_seconds=86400.0, max_entries=32)


def _fix_text(value: Any) -> Any:
    """Undo UTF-8 read as latin-1 ("BolÃ­var" -> "Bolívar") when the round
    trip is clean; anything else is returned unchanged."""
    if not isinstance(value, str) or ("Ã" not in value and "Â" not in value):
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _entry(fuente: str, capa: str) -> dict[str, str]:
    catalogo = _CATALOGO.get(fuente)
    if catalogo is None:
        raise ValueError(f"Fuente '{fuente}' sin capas ArcGIS. Válidas: {', '.join(_CATALOGO)}")
    entry = next((e for e in catalogo if e["capa"] == capa), None)
    if entry is None:
        raise ValueError(
            f"Capa '{capa}' no reconocida en {fuente}. Válidas: "
            f"{', '.join(e['capa'] for e in catalogo)}"
        )
    return entry


async def _get_json(url: str) -> dict[str, Any]:
    raw, truncated = await download_bytes(url)
    if truncated:
        raise ValueError("La respuesta de ArcGIS superó el límite de descarga; reduce count.")
    payload = json.loads(raw.decode("utf-8", errors="replace"))

    # ArcGIS reports errors as HTTP 200 with an "error" object.
    if isinstance(payload, dict) and payload.get("error"):
        error = payload["error"]
        detalle = "; ".join(error.get("details") or [])
        raise ValueError(f"ArcGIS respondió {error.get('code')}: {error.get('message')} {detalle}")
    return payload


async def _layer_meta(url: str) -> dict[str, Any]:
    cached = _meta_cache.get(url)
    if cached is not None:
        return cached
    meta = await _get_json(f"{url}?f=json")
    _meta_cache.set(url, meta)
    return meta


async def search_capas(fuente: str, query: str = "") -> dict[str, Any]:
    """List one source's curated layers, optionally filtered by free text."""
    catalogo = _CATALOGO.get(fuente)
    if catalogo is None:
        raise ValueError(f"Fuente '{fuente}' sin capas ArcGIS. Válidas: {', '.join(_CATALOGO)}")
    q = _strip(query)
    matched = [
        {**e, "tipo_servicio": "ArcGIS REST"}
        for e in catalogo
        if not q or q in _strip(f"{e['capa']} {e['titulo']} {e['descripcion']}")
    ]
    return {
        "total": len(matched),
        "total_en_catalogo": len(catalogo),
        "source": _SOURCES[fuente],
        "capas": matched,
    }


async def get_layer_features(
    fuente: str,
    capa: str,
    count: int = _DEFAULT_FEATURE_COUNT,
    filtro: str = "",
    offset: int = 0,
) -> dict[str, Any]:
    """
    Query one curated layer's attributes.

    Args:
        fuente: arconel or celec.
        capa: A `capa` id from search_capas.
        count: Rows to return (1-500).
        filtro: An ArcGIS SQL where clause (e.g. "Anio = 2024 AND Empresa LIKE
            'CNEL%'"); empty means all rows.
        offset: Rows to skip, for paging through a filtered result.
    """
    entry = _entry(fuente, capa)
    meta = await _layer_meta(entry["url"])
    fechas = {f["name"] for f in meta.get("fields") or [] if f.get("type") == "esriFieldTypeDate"}
    where = filtro.strip() or "1=1"
    capped = max(1, min(count, MAX_FEATURE_COUNT))

    base = {"where": where, "f": "json"}
    total = (
        await _get_json(f"{entry['url']}/query?{urlencode({**base, 'returnCountOnly': 'true'})}")
    )["count"]
    params = {
        **base,
        "outFields": "*",
        "returnGeometry": "false",
        "resultOffset": max(0, offset),
        "resultRecordCount": capped,
    }
    url = f"{entry['url']}/query?{urlencode(params)}"
    payload = await _get_json(url)

    features = []
    for feature in payload.get("features") or []:
        propiedades = {}
        for key, value in (feature.get("attributes") or {}).items():
            if key in fechas and isinstance(value, int | float) and value > 0:
                value = datetime.fromtimestamp(value / 1000, tz=UTC).date().isoformat()
            propiedades[key] = _fix_text(value)
        features.append(
            {
                "id": propiedades.get(meta.get("objectIdField") or "OBJECTID"),
                "tipo_geometria": meta.get("geometryType"),
                "propiedades": propiedades,
            }
        )

    return {
        "capa": capa,
        "titulo": entry["titulo"],
        "filtro": where,
        "offset": max(0, offset),
        "total_features_en_capa": total,
        "features_devueltas": len(features),
        "hay_mas": bool(payload.get("exceededTransferLimit"))
        or max(0, offset) + len(features) < total,
        "campos": [f["name"] for f in meta.get("fields") or []],
        "features": features,
        "url_consulta": url,
    }

"""Client for the IMF's SDMX 2.1 service (`api.imf.org/external/sdmx/2.1`),
no key. Verified live 2026-10-10 (docs/RESEARCH.md § Trigésimo séptima pasada).

NOT Ecuador-only: the `IMF.STA` agency holds ~190 dataflows (CPI, balance of
payments, government finance, monetary data...) for ~200 economies; every
pull defaults to Ecuador.

- `GET /dataflow/IMF.STA` lists the flows (cached).
- `GET /data/IMF.STA,{flow}/{key}` takes a dot-separated key whose dimension
  order differs per flow. A *short* key is a prefix (`ECU` means ECU and every
  value of the other dimensions); a key with too many parts is a 400. The
  response's structure lists the dimensions in key order, which this client
  returns as `dimensiones` so the caller can build a narrower key.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from helpers import sdmx_json
from helpers.cache import TtlCache
from helpers.intl_http import SourceHTTPError, get_json
from helpers.text_utils import strip_accents as _strip

_BASE = "https://api.imf.org/external/sdmx/2.1"
_AGENCY = "IMF.STA"

_flows_cache = TtlCache(ttl_seconds=43200.0, max_entries=2)
_data_cache = TtlCache(ttl_seconds=3600.0, max_entries=128)
_flows_lock = asyncio.Lock()

_FLOW_ID = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_KEY = re.compile(r"^[A-Za-z0-9_.+*-]{0,200}$")
_PERIOD = re.compile(r"^\d{4}(-(M|Q|S)?\d{1,2}|-\d{2}-\d{2})?$")
_DEFAULT_LAST_N = 5
_MAX_LAST_N = 100


async def _fetch_flows() -> list[dict[str, str]]:
    cached = _flows_cache.get("flows")
    if cached is not None:
        return cached
    async with _flows_lock:
        cached = _flows_cache.get("flows")
        if cached is not None:
            return cached
        payload = await get_json(f"{_BASE}/dataflow/{_AGENCY}", fuente="FMI")
        flows = [
            {"flujo": f["id"], "nombre": f.get("name") or ""}
            for f in ((payload or {}).get("data") or {}).get("dataflows", [])
        ]
        if flows:
            _flows_cache.set("flows", flows)
        return flows


async def search_flujos(query: str = "", limit: int = 30) -> dict[str, Any]:
    """List IMF dataflows whose id or name contains `query`."""
    flows = await _fetch_flows()
    q = _strip(query)
    matched = [f for f in flows if not q or q in _strip(f["flujo"]) or q in _strip(f["nombre"])]
    return {
        "total": len(matched),
        "total_catalogo": len(flows),
        "flujos": matched[: max(1, min(limit, 200))],
        "source": "FMI — SDMX (IMF.STA)",
        "url_fuente": "https://data.imf.org/",
    }


async def get_serie(
    flujo: str,
    clave: str = "",
    pais: str = "ECU",
    desde: str = "",
    hasta: str = "",
    ultimos: int = 0,
) -> dict[str, Any]:
    """Series of one IMF dataflow. `clave` empty means the country prefix
    (`pais`); without a period range only the last observations come back."""
    if not _FLOW_ID.match(flujo):
        raise ValueError(f"Código de flujo inválido: {flujo!r}")
    key = clave.strip() or pais.strip().upper()
    if not key or not _KEY.match(key):
        raise ValueError(f"Clave SDMX inválida: {key!r} (ej. ECU o ECU.CPI._T.IX.M)")
    for name, value in (("desde", desde), ("hasta", hasta)):
        if value and not _PERIOD.match(value):
            raise ValueError(f"`{name}` debe ser AAAA, AAAA-MM o AAAA-Mnn para el FMI.")
    params: dict[str, Any] = {}
    if desde:
        params["startPeriod"] = desde
    if hasta:
        params["endPeriod"] = hasta
    if ultimos > 0 or not (desde or hasta):
        params["lastNObservations"] = max(1, min(ultimos or _DEFAULT_LAST_N, _MAX_LAST_N))

    cache_key = (flujo, key, tuple(sorted(params.items())))
    cached = _data_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        payload = await get_json(
            f"{_BASE}/data/{_AGENCY},{flujo}/{key}", fuente="FMI", params=params
        )
    except SourceHTTPError as e:
        # Verified live: an unknown flow is a 404; a key naming a value the
        # flow lacks is a 400 with an unrelated Jackson error message.
        if e.status == 404:
            raise ValueError(
                f"El FMI no tiene el flujo {flujo!r}. Búscalo con `query`."
            ) from e
        if e.status == 400:
            raise ValueError(
                f"El FMI rechazó la clave {key!r} para {flujo} (valor inexistente o "
                "demasiadas partes). Prueba solo el país o revisa `dimensiones`."
            ) from e
        raise
    if payload is None:
        raise ValueError(
            f"El FMI no devolvió datos para {flujo}/{key}. "
            "Busca el flujo con `query` y prueba una clave más corta (solo el país)."
        )
    result = {
        "flujo": flujo,
        "clave_consulta": key,
        **sdmx_json.parse(payload),
        "source": "FMI — SDMX (IMF.STA)",
        "url_fuente": f"https://data.imf.org/en/datasets/IMF.STA:{flujo}",
    }
    if result["series"]:
        _data_cache.set(cache_key, result)
    return result

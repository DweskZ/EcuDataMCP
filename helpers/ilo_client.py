"""Client for ILOSTAT's SDMX service (`sdmx.ilo.org/rest`), no key. Verified
live 2026-10-10 (docs/RESEARCH.md § Trigésimo séptima pasada).

NOT Ecuador-only: ~1,000 labour-market dataflows (`DF_*`) for ~190
economies; pulls default to Ecuador.

- `GET /dataflow/ILO?detail=allstubs` lists the flows (~560 KB, cached).
- `GET /data/ILO,{flow}/{key}?format=jsondata` takes a key whose number of
  dot-separated parts must equal the flow's dimension count (a short key is
  an HTTP 422 "expecting 5 got 1"). The first dimension is the area and the
  second the frequency in the flows checked; to spare the caller the DSD
  lookup, a short key is padded with wildcards using the count the error
  reports, then the call is repeated once.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from helpers import sdmx_json
from helpers.cache import TtlCache
from helpers.intl_http import SourceHTTPError, get_json
from helpers.text_utils import strip_accents as _strip

_BASE = "https://sdmx.ilo.org/rest"
_STRUCTURE = "application/vnd.sdmx.structure+json"

_flows_cache = TtlCache(ttl_seconds=43200.0, max_entries=2)
_data_cache = TtlCache(ttl_seconds=3600.0, max_entries=128)
_flows_lock = asyncio.Lock()

_FLOW_ID = re.compile(r"^[A-Za-z0-9_]{1,80}$")
_KEY = re.compile(r"^[A-Za-z0-9_.+*-]{0,200}$")
_PERIOD = re.compile(r"^\d{4}(-(Q|M|S)?\d{1,2})?$")
_EXPECTING = re.compile(r"expecting (\d+) got (\d+)")
_DEFAULT_LAST_N = 3
_MAX_LAST_N = 100


async def _fetch_flows() -> list[dict[str, str]]:
    cached = _flows_cache.get("flows")
    if cached is not None:
        return cached
    async with _flows_lock:
        cached = _flows_cache.get("flows")
        if cached is not None:
            return cached
        payload = await get_json(
            f"{_BASE}/dataflow/ILO", fuente="OIT", params={"detail": "allstubs"}, accept=_STRUCTURE
        )
        flows = [
            {"flujo": f["id"], "nombre": f.get("name") or ""}
            for f in ((payload or {}).get("data") or {}).get("dataflows", [])
        ]
        if flows:
            _flows_cache.set("flows", flows)
        return flows


async def search_flujos(query: str = "", limit: int = 30) -> dict[str, Any]:
    """List ILOSTAT dataflows whose id or name contains `query`."""
    flows = await _fetch_flows()
    q = _strip(query)
    matched = [f for f in flows if not q or q in _strip(f["flujo"]) or q in _strip(f["nombre"])]
    return {
        "total": len(matched),
        "total_catalogo": len(flows),
        "flujos": matched[: max(1, min(limit, 200))],
        "source": "OIT — ILOSTAT (SDMX)",
        "url_fuente": "https://ilostat.ilo.org/data/",
    }


async def get_serie(
    flujo: str,
    clave: str = "",
    pais: str = "ECU",
    desde: str = "",
    hasta: str = "",
    ultimos: int = 0,
) -> dict[str, Any]:
    """Series of one ILOSTAT dataflow; `clave` empty means the country
    followed by wildcards."""
    flujo = flujo.strip()
    if not flujo.upper().startswith("DF_"):
        flujo = f"DF_{flujo}"
    if not _FLOW_ID.match(flujo):
        raise ValueError(f"Código de flujo inválido: {flujo!r}")
    key = clave.strip() or pais.strip().upper()
    if not key or not _KEY.match(key):
        raise ValueError(f"Clave SDMX inválida: {key!r} (ej. ECU.A o ECU.A...)")
    for name, value in (("desde", desde), ("hasta", hasta)):
        if value and not _PERIOD.match(value):
            raise ValueError(f"`{name}` debe ser AAAA o AAAA-Qn / AAAA-Mnn para la OIT.")
    params: dict[str, Any] = {"format": "jsondata"}
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
    url = f"{_BASE}/data/ILO,{flujo}"
    try:
        payload = await get_json(f"{url}/{key}", fuente="OIT", params=params)
    except SourceHTTPError as e:
        match = _EXPECTING.search(e.body)
        if e.status == 404:
            raise ValueError(
                f"La OIT no tiene datos para {flujo}/{key} (flujo o clave inexistente). "
                "Busca el flujo con `query`."
            ) from e
        wanted = int(match.group(1)) if match else 0
        parts = key.split(".")
        if e.status != 422 or len(parts) >= wanted:
            raise
        key = ".".join(parts + [""] * (wanted - len(parts)))
        payload = await get_json(f"{url}/{key}", fuente="OIT", params=params)
    if payload is None:
        raise ValueError(f"La OIT no devolvió datos para {flujo}/{key}.")
    result = {
        "flujo": flujo,
        "clave_consulta": key,
        **sdmx_json.parse(payload),
        "source": "OIT — ILOSTAT (SDMX)",
        "url_fuente": "https://ilostat.ilo.org/data/",
    }
    if result["series"]:
        _data_cache.set(cache_key, result)
    return result

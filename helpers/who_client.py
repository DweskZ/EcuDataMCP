"""Client for the WHO Global Health Observatory OData API
(`ghoapi.azureedge.net/api`), no key. Verified live 2026-10-10
(docs/RESEARCH.md § Trigésimo séptima pasada).

NOT Ecuador-only: ~2,000 indicators for ~190 countries; every pull is
filtered to one country (`SpatialDim eq 'ECU'`, default Ecuador).

- `GET /api/Indicator` is the indicator catalog (cached, searched locally,
  like the WDI client).
- `GET /api/{IndicatorCode}?$filter=SpatialDim eq 'ECU'` returns one row per
  year and breakdown (sex, age group...), with the numeric value and, when
  published, the confidence bounds.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from helpers.cache import TtlCache
from helpers.intl_http import get_json
from helpers.text_utils import strip_accents as _strip

_BASE = "https://ghoapi.azureedge.net/api"

_catalog_cache = TtlCache(ttl_seconds=43200.0, max_entries=2)
_data_cache = TtlCache(ttl_seconds=3600.0, max_entries=256)
_catalog_lock = asyncio.Lock()

_INDICATOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,79}$")
_COUNTRY = re.compile(r"^[A-Za-z]{3}$")


async def _fetch_catalog() -> list[dict[str, str]]:
    cached = _catalog_cache.get("who")
    if cached is not None:
        return cached
    async with _catalog_lock:
        cached = _catalog_cache.get("who")
        if cached is not None:
            return cached
        payload = await get_json(f"{_BASE}/Indicator", fuente="OMS")
        catalog = [
            {"indicador": i["IndicatorCode"], "nombre": i.get("IndicatorName") or ""}
            for i in (payload or {}).get("value", [])
        ]
        if catalog:
            _catalog_cache.set("who", catalog)
        return catalog


async def search_indicadores(query: str = "", limit: int = 30) -> dict[str, Any]:
    """Search the GHO indicator catalog by code or name."""
    catalog = await _fetch_catalog()
    q = _strip(query)
    matched = [i for i in catalog if not q or q in _strip(i["indicador"]) or q in _strip(i["nombre"])]
    return {
        "total": len(matched),
        "total_catalogo": len(catalog),
        "indicadores": matched[: max(1, min(limit, 200))],
        "source": "Global Health Observatory — OMS",
        "url_fuente": "https://www.who.int/data/gho/data/indicators",
    }


async def get_indicador(
    indicador: str, pais: str = "ECU", desde: int | None = None, hasta: int | None = None
) -> dict[str, Any]:
    """One GHO indicator for one country (ISO3), optionally a year range."""
    if not _INDICATOR.match(indicador):
        raise ValueError(f"Código de indicador inválido: {indicador!r}")
    if not _COUNTRY.match(pais):
        raise ValueError(f"Código de país inválido: {pais!r} (usa ISO3, p. ej. ECU)")
    if desde is not None and hasta is not None and desde > hasta:
        raise ValueError("`desde` no puede ser mayor que `hasta`.")
    clauses = [f"SpatialDim eq '{pais.upper()}'"]
    if desde is not None:
        clauses.append(f"TimeDim ge {desde}")
    if hasta is not None:
        clauses.append(f"TimeDim le {hasta}")
    params = {"$filter": " and ".join(clauses)}
    cache_key = (indicador, params["$filter"])
    cached = _data_cache.get(cache_key)
    if cached is not None:
        return cached

    payload = await get_json(f"{_BASE}/{indicador}", fuente="OMS", params=params)
    rows = (payload or {}).get("value", [])
    if not rows:
        raise ValueError(
            f"La OMS no tiene datos de {indicador} para {pais.upper()} "
            "(¿código inexistente? búscalo con `query`)."
        )
    serie = [
        {
            "anio": r.get("TimeDim"),
            "desglose": ", ".join(str(r[k]) for k in ("Dim1", "Dim2", "Dim3") if r.get(k)) or None,
            "valor": r.get("NumericValue") if r.get("NumericValue") is not None else r.get("Value"),
            "bajo": r.get("Low"),
            "alto": r.get("High"),
        }
        for r in rows
    ]
    serie.sort(key=lambda r: (r["anio"] is None, r["anio"], r["desglose"] or ""))
    names = {i["indicador"]: i["nombre"] for i in _catalog_cache.get("who") or []}
    result = {
        "indicador": indicador,
        "nombre": names.get(indicador),
        "pais": pais.upper(),
        "total_registros": len(serie),
        "serie": serie,
        "source": "Global Health Observatory — OMS",
        "url_fuente": f"https://www.who.int/data/gho/data/indicators/indicator-details/GHO/{indicador}",
    }
    _data_cache.set(cache_key, result)
    return result

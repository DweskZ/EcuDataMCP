"""Client for the World Bank's World Development Indicators (WDI), served by
the public v2 API (api.worldbank.org), no key. Verified live 2026-10-01
(docs/RESEARCH.md § Trigésimo quinta pasada).

NOT Ecuador-only: WDI covers ~200 economies and 1,400+ indicators; every
data pull here defaults to Ecuador (`pais="ECU"`) because that is this
project's scope. Two endpoints:

- `/v2/indicator?source=2` — the WDI indicator catalog (~1.4 MB, cached).
- `/v2/country/{iso3}/indicator/{id}` — one series for one country, one row
  per year, newest first; `date=YYYY:YYYY` restricts the range.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://api.worldbank.org/v2"
_SOURCE_WDI = 2
_FIRST_YEAR = 1960  # WDI series start in 1960 at the earliest

# The catalog changes a few times a year; the series refresh with each WDI
# release, so a day is enough for data.
_catalog_cache = TtlCache(ttl_seconds=43200.0, max_entries=2)
_data_cache = TtlCache(ttl_seconds=3600.0, max_entries=256)
_catalog_lock = asyncio.Lock()

_INDICATOR_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")
_COUNTRY_ID = re.compile(r"^[A-Za-z]{2,3}$")


async def _fetch_json(path: str, **params: Any) -> Any:
    query = urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{_BASE}{path}?{query}"
    logger.info("WDI GET %s", url)
    content, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(f"La respuesta de {url} superó el límite de descarga.")
    return json.loads(content)


def _check_api_error(payload: Any) -> list[Any]:
    """The API reports errors as a one-element list holding a `message` list
    (HTTP 200), so a bad indicator or country id must be detected here."""
    if not isinstance(payload, list) or not payload:
        raise ValueError("Respuesta inesperada de la API del Banco Mundial.")
    head = payload[0]
    if isinstance(head, dict) and head.get("message"):
        msg = head["message"][0]
        raise ValueError(f"{msg.get('key')}: {msg.get('value')}")
    return payload


async def _fetch_catalog() -> list[dict[str, Any]]:
    cached = _catalog_cache.get("wdi")
    if cached is not None:
        return cached
    async with _catalog_lock:
        cached = _catalog_cache.get("wdi")
        if cached is not None:
            return cached
        payload = _check_api_error(
            await _fetch_json("/indicator", source=_SOURCE_WDI, format="json", per_page=5000)
        )
        catalog = [
            {
                # The API sends null as well as "" for missing text fields.
                "indicador": i["id"],
                "nombre": i.get("name") or "",
                "descripcion": i.get("sourceNote") or "",
                "organizacion": i.get("sourceOrganization") or "",
            }
            for i in payload[1] or []
        ]
        if catalog:
            _catalog_cache.set("wdi", catalog)
        return catalog


async def search_indicadores(query: str = "", limit: int = 30) -> dict[str, Any]:
    """Search the WDI catalog by indicator id, name or description."""
    catalog = await _fetch_catalog()
    q = _strip(query)
    matched = [
        i
        for i in catalog
        if not q or q in _strip(i["indicador"]) or q in _strip(i["nombre"]) or q in _strip(i["descripcion"])
    ]
    return {
        "total": len(matched),
        "total_catalogo": len(catalog),
        "indicadores": matched[: max(1, min(limit, 200))],
        "source": "World Development Indicators — Banco Mundial",
        "url_fuente": "https://databank.worldbank.org/source/world-development-indicators",
    }


async def get_indicador(
    indicador: str, pais: str = "ECU", desde: int | None = None, hasta: int | None = None
) -> dict[str, Any]:
    """One WDI series for one country (ISO3/ISO2 code), optionally a year
    range; a single bound runs from 1960 or up to the current year."""
    if not _INDICATOR_ID.match(indicador):
        raise ValueError(f"Código de indicador inválido: {indicador!r}")
    if not _COUNTRY_ID.match(pais):
        raise ValueError(f"Código de país inválido: {pais!r} (usa ISO3, p. ej. ECU)")
    # The API only takes a closed `date=YYYY:YYYY` range, so close an open one.
    if desde is not None and hasta is None:
        hasta = datetime.now(UTC).year
    elif hasta is not None and desde is None:
        desde = _FIRST_YEAR
    if desde is not None and hasta is not None and desde > hasta:
        raise ValueError("`desde` no puede ser mayor que `hasta`.")

    params: dict[str, Any] = {"format": "json", "per_page": 1000}
    if desde is not None:
        params["date"] = f"{desde}:{hasta}"
    cache_key = f"{pais.upper()}:{indicador}:{params.get('date')}"
    cached = _data_cache.get(cache_key)
    if cached is not None:
        return cached

    payload = _check_api_error(
        await _fetch_json(f"/country/{pais.upper()}/indicator/{indicador}", **params)
    )
    meta, rows = payload[0], payload[1] or []
    # Almost every WDI series is yearly; a quarterly/monthly one ("2020Q1")
    # keeps its period label instead of failing the int() conversion.
    serie = [
        {"anio": int(r["date"]) if str(r["date"]).isdigit() else r["date"], "valor": r["value"]}
        for r in rows
        if r.get("value") is not None
    ]
    serie.sort(key=lambda r: str(r["anio"]))
    result = {
        "indicador": indicador,
        "nombre": rows[0]["indicator"]["value"] if rows else None,
        "pais": rows[0]["country"]["value"] if rows else pais.upper(),
        "total_registros": len(serie),
        "anios_sin_dato": sum(1 for r in rows if r.get("value") is None),
        "serie": serie,
        "ultima_actualizacion": meta.get("lastupdated"),
        "source": "World Development Indicators — Banco Mundial",
        "url_fuente": f"https://data.worldbank.org/indicator/{indicador}?locations={pais.upper()}",
    }
    if serie:
        _data_cache.set(cache_key, result)
    return result

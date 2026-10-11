"""Client for the UNHCR Refugee Data Finder population API
(`api.unhcr.org/population/v1/population/`), no key. Verified live
2026-10-10 (docs/RESEARCH.md § Trigésimo séptima pasada).

NOT Ecuador-only: it holds displaced and stateless population by country of
asylum (`coa`) and of origin (`coo`), per year; this client pins the country
of asylum (default Ecuador). Three shapes:

- no `origen`: one totals row per year (all origins together);
- `origen` = ISO3 (e.g. VEN): that origin only;
- `origen` = "todos": one row per country of origin and year.

Responses are paginated (`page`, `maxPages`); pages are followed up to a cap.
Numbers arrive mixed (ints, "0" strings, "-" for not available) and are
normalised to int or None.
"""

from __future__ import annotations

import re
from typing import Any

from helpers.cache import TtlCache
from helpers.intl_http import get_json

_URL = "https://api.unhcr.org/population/v1/population/"
_PAGE_SIZE = 1000
_MAX_PAGES = 10

_data_cache = TtlCache(ttl_seconds=3600.0, max_entries=64)
_COUNTRY = re.compile(r"^[A-Za-z]{3}$")
_FIELDS = {
    "refugees": "refugiados",
    "asylum_seekers": "solicitantes_asilo",
    "returned_refugees": "refugiados_retornados",
    "idps": "desplazados_internos",
    "returned_idps": "desplazados_retornados",
    "stateless": "apatridas",
    "ooc": "otras_personas_de_preocupacion",
    "oip": "otras_personas_necesitan_proteccion_internacional",
    "hst": "poblacion_anfitriona_apatrida",
}


def _count(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw
    try:
        return int(str(raw).replace(",", ""))
    except ValueError:
        return None  # "-" means not available


async def get_poblacion(
    pais: str = "ECU", origen: str = "", desde: int | None = None, hasta: int | None = None
) -> dict[str, Any]:
    """Population of concern in country of asylum `pais`, per year."""
    if not _COUNTRY.match(pais):
        raise ValueError(f"Código de país inválido: {pais!r} (usa ISO3, p. ej. ECU)")
    origen = origen.strip()
    if origen and origen.lower() != "todos" and not _COUNTRY.match(origen):
        raise ValueError("`socio`/origen debe ser un ISO3 (ej. VEN) o 'todos'.")
    if desde is not None and hasta is not None and desde > hasta:
        raise ValueError("`desde` no puede ser mayor que `hasta`.")
    params: dict[str, Any] = {"coa": pais.upper(), "limit": _PAGE_SIZE}
    # `year=2023,2024` silently returns only the first year; yearFrom/yearTo
    # is the working range filter (verified live).
    if desde is not None:
        params["yearFrom"] = desde
    if hasta is not None:
        params["yearTo"] = hasta
    if origen.lower() == "todos":
        params["coo_all"] = "true"
    elif origen:
        params["coo"] = origen.upper()

    cache_key = tuple(sorted(params.items()))
    cached = _data_cache.get(cache_key)
    if cached is not None:
        return cached

    items: list[dict[str, Any]] = []
    max_pages = 1
    page = 1
    while page <= min(max_pages, _MAX_PAGES):
        payload = await get_json(_URL, fuente="ACNUR", params={**params, "page": page})
        items += (payload or {}).get("items", [])
        max_pages = int((payload or {}).get("maxPages") or 1)
        page += 1
    rows = [
        {
            "anio": r.get("year"),
            "origen": r.get("coo") if r.get("coo") not in (None, "-") else "Total",
            "origen_nombre": r.get("coo_name") if r.get("coo_name") not in (None, "-") else "Todos los orígenes",
            **{es: _count(r.get(en)) for en, es in _FIELDS.items()},
        }
        for r in items
    ]
    rows.sort(key=lambda r: (r["anio"] or 0, r["origen"]))
    result = {
        "pais": pais.upper(),
        "total_registros": len(rows),
        "paginas_leidas": min(max_pages, _MAX_PAGES),
        "paginas_totales": max_pages,
        "registros": rows,
        "source": "UNHCR — Refugee Data Finder",
        "url_fuente": f"https://www.unhcr.org/refugee-statistics/download/?url=&coa={pais.upper()}",
    }
    if rows:
        _data_cache.set(cache_key, result)
    return result

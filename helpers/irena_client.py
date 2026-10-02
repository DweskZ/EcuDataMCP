"""Client for IRENASTAT, the International Renewable Energy Agency's PxWeb
API (pxweb.irena.org), no key. Verified live 2026-10-01 (docs/RESEARCH.md §
Trigésimo quinta pasada).

NOT Ecuador-only: the country table covers 224 countries/areas, 2000 on,
electricity generation (GWh) and installed capacity (MW) in 26 technologies.
Every pull defaults to Ecuador (`ECU`).

The table id carries the edition (`Country_ELECSTAT_2026_H2_PX.px`), so it
is discovered from the folder listing instead of hard-coded. PxWeb takes
value *codes* in queries (`ECU`, `0`...), not labels, so the metadata is
read first to resolve a country name or code and to label the cells.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import quote

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes, post_json_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_FOLDER = "https://pxweb.irena.org/api/v1/en/IRENASTAT/Power%20Capacity%20and%20Generation"
_TABLE_PREFIX = "Country_ELECSTAT_"

_table_cache = TtlCache(ttl_seconds=43200.0, max_entries=4)
_data_cache = TtlCache(ttl_seconds=3600.0, max_entries=64)
_lock = asyncio.Lock()


async def _request(url: str, body: dict[str, Any] | None = None) -> Any:
    logger.info("IRENASTAT %s %s", "POST" if body else "GET", url)
    if body is None:
        content, truncated = await download_bytes(url)
    else:
        content, truncated = await post_json_bytes(url, body)
    if truncated:
        raise ValueError(f"La respuesta de {url} superó el límite de descarga.")
    return json.loads(content)


async def _table() -> dict[str, Any]:
    """Current country table: its id, URL and variable metadata."""
    cached = _table_cache.get("country")
    if cached is not None:
        return cached
    async with _lock:
        cached = _table_cache.get("country")
        if cached is not None:
            return cached
        listing = await _request(_FOLDER)
        tables = [t for t in listing if t.get("id", "").startswith(_TABLE_PREFIX)]
        if not tables:
            raise ValueError("No se encontró la tabla de estadísticas por país en IRENASTAT.")
        # Editions sort lexicographically (2026_H2 > 2026_H1 > 2025_H2).
        table = max(tables, key=lambda t: t["id"])
        url = f"{_FOLDER}/{quote(table['id'])}"
        meta = await _request(url)
        info = {
            "id": table["id"],
            "url": url,
            "actualizado": table.get("updated"),
            "variables": {v["code"]: v for v in meta["variables"]},
        }
        _table_cache.set("country", info)
        return info


def _resolve_country(variable: dict[str, Any], pais: str) -> tuple[str, str]:
    q = _strip(pais)
    pairs = list(zip(variable["values"], variable["valueTexts"], strict=True))
    for code, text in pairs:
        if _strip(code) == q or _strip(text) == q:
            return code, text
    partial = [(c, t) for c, t in pairs if q and q in _strip(t)]
    if len(partial) == 1:
        return partial[0]
    raise ValueError(
        f"País no encontrado o ambiguo: {pais!r}"
        + (f" (candidatos: {', '.join(t for _, t in partial[:8])})" if partial else "")
    )


def _dim(available: list[str], name: str, tabla: str) -> str:
    """The dimension id matching `name`, ignoring case and spacing, so a new
    edition that only re-capitalizes a dimension still parses; a real rename
    fails with the names the table does have."""
    key = name.replace(" ", "").lower()
    for d in available:
        if d.replace(" ", "").lower() == key:
            return d
    raise ValueError(
        f"La tabla {tabla} de IRENASTAT no tiene la dimensión {name!r} "
        f"(tiene: {', '.join(available)}); su estructura cambió."
    )


async def get_electricidad(
    pais: str = "ECU",
    tecnologia: str = "",
    tipo: str = "ambos",
    conexion: str = "All",
    desde: int | None = None,
    hasta: int | None = None,
) -> dict[str, Any]:
    """
    Installed capacity (MW) and/or generation (GWh) of one country by
    technology and year.

    Args:
        pais: ISO3 code or English country name (default "ECU").
        tecnologia: Case-insensitive substring of the technology label
            (e.g. "solar", "hydro", "Total Renewable"); empty = all 26.
        tipo: "generacion" (GWh), "capacidad" (MW) or "ambos".
        conexion: "All" (default), "On-grid" or "Off-grid".
        desde / hasta: Inclusive year bounds.
    """
    tipo_norm = _strip(tipo)
    if tipo_norm not in {"generacion", "capacidad", "ambos"}:
        raise ValueError("`tipo` debe ser generacion, capacidad o ambos.")
    if desde is not None and hasta is not None and desde > hasta:
        raise ValueError("`desde` no puede ser mayor que `hasta`.")

    table = await _table()
    variables = table["variables"]
    country_dim = _dim(list(variables), "Country/area", table["id"])
    code, country_name = _resolve_country(variables[country_dim], pais)

    cache_key = f"{table['id']}:{code}"
    payload = _data_cache.get(cache_key)
    if payload is None:
        body = {
            "query": [
                {"code": country_dim, "selection": {"filter": "item", "values": [code]}}
            ],
            "response": {"format": "json-stat2"},
        }
        payload = await _request(table["url"], body)
        _data_cache.set(cache_key, payload)

    dims = payload["id"]
    labels = {
        d: {c: payload["dimension"][d]["category"]["label"][c] for c in payload["dimension"][d]["category"]["index"]}
        for d in dims
    }
    order = {d: list(payload["dimension"][d]["category"]["index"]) for d in dims}
    sizes = payload["size"]
    values = payload["value"]
    tech_dim, type_dim, conn_dim, year_dim = (
        _dim(dims, n, table["id"]) for n in ("Technology", "Data Type", "Grid connection", "Year")
    )

    want_tech = _strip(tecnologia)
    want_conn = _strip(conexion)
    rows: list[dict[str, Any]] = []
    # json-stat2 stores cells row-major in `dims` order; iterate that order.
    stride = [1] * len(dims)
    for i in range(len(dims) - 2, -1, -1):
        stride[i] = stride[i + 1] * sizes[i + 1]
    for idx, valor in enumerate(values):
        if valor is None:
            continue
        pos = {d: order[d][(idx // stride[i]) % sizes[i]] for i, d in enumerate(dims)}
        tech = labels[tech_dim][pos[tech_dim]]
        dtype = labels[type_dim][pos[type_dim]]
        conn = labels[conn_dim][pos[conn_dim]]
        year = int(labels[year_dim][pos[year_dim]])
        if want_tech and want_tech not in _strip(tech):
            continue
        if _strip(conn) != want_conn:
            continue
        is_gen = "generation" in dtype.lower()
        if (tipo_norm == "generacion" and not is_gen) or (tipo_norm == "capacidad" and is_gen):
            continue
        if (desde is not None and year < desde) or (hasta is not None and year > hasta):
            continue
        rows.append(
            {
                "tecnologia": tech,
                "tipo": "generacion_gwh" if is_gen else "capacidad_mw",
                "conexion": conn,
                "anio": year,
                "valor": valor,
            }
        )
    rows.sort(key=lambda r: (r["tecnologia"], r["tipo"], r["anio"]))
    return {
        "pais": country_name,
        "codigo_pais": code,
        "total_registros": len(rows),
        "registros": rows,
        "tabla": table["id"],
        "actualizado": table.get("actualizado"),
        "source": "IRENASTAT — IRENA",
        "url_fuente": "https://pxweb.irena.org/pxweb/en/IRENASTAT/",
    }

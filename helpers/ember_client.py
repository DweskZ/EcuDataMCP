"""Ember electricity data for Ecuador, through Our World in Data.

Ember's own API needs a key (403 "No API key set" without one, checked
2026-11-07) and its bulk CSVs are 49-70 MB, far over the 5 MB cap. Our World
in Data republishes Ember's yearly and monthly electricity data (CC BY 4.0)
in its "electricity-mix" explorer, which serves one country's series as a
small CSV:

    /grapher/electricity-mix.csv?metric=..&source=..&frequency=..
        &country=~ECU&csvType=filtered&tab=chart

`tab=chart` matters: without it the explorer returns only the latest year.
Ecuador has monthly data from 2019-01 (88 months to 2026-04 when checked)
and yearly data back to 1965 for generation. The explorer's views are
metric x source x frequency; _VIEWS lists the ones it defines.
"""

from __future__ import annotations

import asyncio
import csv
import io
from typing import Any
from urllib.parse import urlencode

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.text_utils import strip_accents

_BASE = "https://ourworldindata.org/grapher/electricity-mix.csv"
_PAGE = "https://ourworldindata.org/electricity-mix"

_ALL_SOURCES = (
    "total", "coal", "gas", "oil", "fossil", "hydro", "solar", "wind",
    "solar_and_wind", "bioenergy", "other_renewables", "renewables",
    "nuclear", "low_carbon",
)
_GROUPS = ("total", "fossil", "low_carbon", "renewables", "solar_and_wind")

# metric -> (allowed sources, unit, description)
_VIEWS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "generation": (_ALL_SOURCES, "TWh", "Electricity generation"),
    "share_of_generation": (tuple(s for s in _ALL_SOURCES if s != "total"), "%", "Share of generation"),
    "per_capita": (_ALL_SOURCES, "kWh per person", "Generation per person"),
    "by_source": (_GROUPS, "TWh", "Generation by source (one column per source)"),
    "by_source_per_capita": (_GROUPS, "kWh per person", "Generation per person by source"),
    "demand": (("total",), "TWh", "Electricity demand"),
    "demand_per_capita": (("total",), "kWh per person", "Electricity demand per person"),
    "net_imports": (("total",), "TWh", "Net electricity imports"),
    "imports_share": (("total",), "% of demand", "Net imports as share of demand"),
    "carbon_intensity": (("total",), "gCO2/kWh", "Carbon intensity of electricity"),
}
_FREQUENCIES = {"A": "annual", "M": "monthly"}

# The explorer's monthly by-source views come back empty (header only,
# checked 2026-11-07) while every single-source monthly view has data, so
# the monthly breakdown is assembled from those.
_GROUP_MEMBERS = {
    "total": ("coal", "gas", "oil", "hydro", "solar", "wind", "bioenergy", "other_renewables", "nuclear"),
    "fossil": ("coal", "gas", "oil"),
    "renewables": ("hydro", "solar", "wind", "bioenergy", "other_renewables"),
    "low_carbon": ("hydro", "solar", "wind", "bioenergy", "other_renewables", "nuclear"),
    "solar_and_wind": ("solar", "wind"),
}

_cache = TtlCache(ttl_seconds=43200.0, max_entries=64, persist="ember_owid")


def catalog(query: str = "") -> list[dict[str, Any]]:
    """Every view as an `indicador` id ("metric/source"), filtered by text."""
    q = strip_accents(query)
    rows = []
    for metric, (sources, unit, label) in _VIEWS.items():
        for source in sources:
            ident = f"{metric}/{source}"
            text = f"{ident} {label} {unit}".replace("_", " ")
            if q and not all(word in strip_accents(text) for word in q.split()):
                continue
            rows.append(
                {
                    "indicador": ident,
                    "nombre": f"{label} — {source.replace('_', ' ')}",
                    "unidad": unit,
                    "frecuencias": ["A", "M"],
                }
            )
    return rows


def _parse_indicador(indicador: str) -> tuple[str, str]:
    metric, _, source = indicador.strip().lower().partition("/")
    source = source or "total"
    if metric not in _VIEWS:
        raise ValueError(
            f"indicador '{indicador}' no existe. Usa la forma metrica/fuente, "
            f"p. ej. generation/hydro; métricas: {', '.join(_VIEWS)}. Sin indicador lista el catálogo."
        )
    if source not in _VIEWS[metric][0]:
        raise ValueError(
            f"La métrica {metric} no tiene la fuente '{source}'; disponibles: "
            f"{', '.join(_VIEWS[metric][0])}."
        )
    return metric, source


def parse_csv(text: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    """(period column, value columns, rows) from an explorer CSV.

    Single-indicator views carry Entity, Code, Year|Month, value; the
    by-source views drop Code. Empty cells become None.
    """
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    period = next((f for f in fields if f in ("Year", "Month", "Day")), None)
    if period is None:
        raise ValueError(f"Respuesta inesperada de Our World in Data (columnas: {fields[:6]}).")
    values = [f for f in fields if f not in ("Entity", "Code", period)]
    rows = []
    for row in reader:
        parsed: dict[str, Any] = {}
        for col in values:
            cell = (row.get(col) or "").strip()
            try:
                parsed[col] = float(cell) if cell else None
            except ValueError:
                parsed[col] = cell
        rows.append({"periodo": row[period], "entidad": row.get("Entity"), "valores": parsed})
    return period, values, rows


async def _fetch_fresh(url: str) -> str:
    cached = _cache.get(url)
    if cached is not None:
        return cached
    raw, truncated = await download_bytes(url)
    if truncated:
        raise ValueError("La serie de Our World in Data superó el límite de descarga.")
    text = raw.decode("utf-8", errors="replace")
    if text.lstrip().startswith("{"):
        raise ValueError(f"Our World in Data no devolvió un CSV: {text[:120]}")
    _cache.set(url, text)
    return text


async def _fetch(url: str) -> str:
    """Fresh fetch, or the last good copy when the source fails (see TtlCache.serve_stale)."""
    try:
        return await _fetch_fresh(url)
    except Exception as exc:
        stale = _cache.serve_stale(url, exc)
        if stale is None:
            raise
        return stale


def _url(metric: str, source: str, freq: str, iso3: str) -> str:
    return f"{_BASE}?" + urlencode(
        {
            "metric": metric,
            "source": source,
            "frequency": freq,
            "country": f"~{iso3}",
            "csvType": "filtered",
            "tab": "chart",
        }
    )


async def _monthly_by_source(metric: str, source: str, iso3: str) -> tuple[list[str], list[dict[str, Any]], str]:
    """Join the single-source monthly series into one row per month."""
    single = "per_capita" if metric == "by_source_per_capita" else "generation"
    members = _GROUP_MEMBERS[source]
    urls = [_url(single, m, "monthly", iso3) for m in members]
    texts = await asyncio.gather(*(_fetch(u) for u in urls))
    columns: list[str] = []
    merged: dict[str, dict[str, Any]] = {}
    for text in texts:
        _period, cols, rows = parse_csv(text)
        columns += [c for c in cols if c not in columns]
        for r in rows:
            entry = merged.setdefault(r["periodo"], {"periodo": r["periodo"], "entidad": r["entidad"], "valores": {}})
            entry["valores"].update(r["valores"])
    return columns, [merged[k] for k in sorted(merged)], urls[0]


async def get_serie(
    indicador: str,
    pais: str = "ECU",
    frecuencia: str = "A",
    desde: str = "",
    hasta: str = "",
) -> dict[str, Any]:
    """One Ember series for one country (ISO3), yearly (A) or monthly (M)."""
    metric, source = _parse_indicador(indicador)
    freq = _FREQUENCIES.get(frecuencia.upper())
    if freq is None:
        raise ValueError("frecuencia debe ser A (anual) o M (mensual).")
    iso3 = (pais or "ECU").strip().upper()
    if freq == "monthly" and metric in ("by_source", "by_source_per_capita"):
        columns, rows, url = await _monthly_by_source(metric, source, iso3)
    else:
        url = _url(metric, source, freq, iso3)
        _period, columns, rows = parse_csv(await _fetch(url))
    if desde:
        rows = [r for r in rows if r["periodo"] >= desde]
    if hasta:
        rows = [r for r in rows if r["periodo"][: len(hasta)] <= hasta]
    _sources, unit, label = _VIEWS[metric]
    return {
        "indicador": f"{metric}/{source}",
        "nombre": label,
        "unidad": unit,
        "frecuencia": "mensual" if freq == "monthly" else "anual",
        "pais": iso3,
        "columnas": columns,
        "total_registros": len(rows),
        "registros": rows,
        "source": "Ember (Yearly/Monthly Electricity Data), vía Our World in Data",
        "url_fuente": _PAGE,
        "url_consulta": url,
        "licencia": "CC BY 4.0",
    }


async def search_indicadores(query: str = "", limit: int = 30) -> dict[str, Any]:
    rows = catalog(query)
    return {
        "total": len(rows),
        "total_catalogo": len(catalog()),
        "indicadores": rows[: max(1, min(limit, 200))],
        "source": "Ember (Yearly/Monthly Electricity Data), vía Our World in Data",
        "url_fuente": _PAGE,
    }

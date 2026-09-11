"""Client for BCE's statistical publication calendar (contenido.bce.fin.ec)
-- the "calendario de publicaciones futuras" gap left open in RESEARCH.md's
Duodécima pasada ("search_bce_publicaciones solo expone ventana rodante...
falta... el calendario de publicaciones futuras").

Confirmed live 2026-09-09: `calendario-estadistico/` (the page's own menu
label) is not itself the data -- it only embeds an `<iframe>` pointing at
`/documentos/CalendarioEstadistico/ConsultaCalendario.html`, a small static
single-page app (`ConsultaCalendario.js`) that renders a filterable table
from one plain CSV it fetches itself:
`/documentos/CalendarioEstadistico/calendario_publicaciones.csv`. No
JS execution needed -- this client reads that CSV directly.

The CSV is UTF-8 with a BOM (confirmed live: decoding as cp1252 instead
produces "PUBLICACIÃ“N"-style mangled text; `utf-8-sig` decodes it
cleanly), semicolon-delimited, one row per scheduled release. Confirmed
live 2026-09-09: 523 rows, dates spanning the full 2026 calendar year
(2026-01-05 to 2026-12-31, no year in the filename so presumably
overwritten in place for next year rather than replaced by a dated
sibling), 162 of them genuinely in the future relative to the fetch date --
real forward-looking release dates for IEM, Cuentas Nacionales, IMAEc,
balance of payments, and more, each with a category/periodicity and a
direct BCE link to the publication's own page.

Two columns are deliberately dropped from what this client exposes:
"RESPONSABLE" and "CORREO DEL RESPONSABLE" are the individual BCE staff
member's name and work email assigned to that release -- real, direct
personal identifiers with no relevance to "when does X get published",
which is the only thing this tool is for. Every other column (dates,
publication name, type, periodicity, reference period, category, link,
and any free-text "Observaciones" note) is kept as-is.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.text_utils import strip_accents as _strip

_CSV_URL = "https://contenido.bce.fin.ec/documentos/CalendarioEstadistico/calendario_publicaciones.csv"
_PAGE_URL = "https://contenido.bce.fin.ec/calendario-estadistico/"
_SOURCE_NAME = "Banco Central del Ecuador — Calendario de Publicaciones Estadísticas"

# BCE amends specific release dates through the year (see "Observaciones"
# notes referencing INEC's own delivery schedule) -- same TTL rationale as
# every other BCE publication-list client in this project (bce_remesas_client,
# bce_precios_comex_client, bce_indices_client): a few hours balances
# staleness against re-fetching on every call.
_calendario_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)

_COLUMN_MAP = {
    "TIPO DE PUBLICACIÓN": "tipo",
    "NOMBRE DE LA PUBLICACIÓN": "nombre",
    "OPERACIÓN ESTADÍSTICA A LA QUE PERTENECE": "operacion_estadistica",
    "PERIODICIDAD": "periodicidad",
    "PERÍODO DE REFERENCIA": "periodo_referencia",
    "FECHA DE CORTE": "fecha_corte",
    "DÍA": "dia_semana",
    "MES": "mes",
    "Observaciones": "observaciones",
    "Categoría de Publicaciones": "categoria",
    "Enlace": "enlace",
}


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _parse_fecha(raw: str) -> str | None:
    """"14/1/2026" (D/M/YYYY, not zero-padded) -> "2026-01-14"."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d/%m/%Y").replace(tzinfo=UTC).date().isoformat()
    except ValueError:
        return None


def _parse_row(row: dict[str, str]) -> dict[str, Any] | None:
    fecha = _parse_fecha(row.get("FECHA", ""))
    if fecha is None:
        return None
    entry: dict[str, Any] = {"fecha": fecha}
    for source, target in _COLUMN_MAP.items():
        entry[target] = _clean(row.get(source))
    return entry


async def _fetch_calendario() -> list[dict[str, Any]]:
    cached = _calendario_cache.get("calendario")
    if cached is not None:
        return cached

    content, truncated = await download_bytes(_CSV_URL)
    if truncated:
        raise ValueError("El calendario de publicaciones del BCE superó el límite de descarga.")
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    entries = [parsed for row in reader if (parsed := _parse_row(row)) is not None]
    entries.sort(key=lambda e: e["fecha"])
    if entries:
        # Same "don't cache an apparently-broken/empty scrape" rationale as
        # every other BCE publication-list client in this project.
        _calendario_cache.set("calendario", entries)
    return entries


def clear_cache() -> None:
    """Clear the calendar cache; useful for refresh jobs and tests."""
    _calendario_cache.clear()


async def search_calendario(
    query: str = "",
    categoria: str = "",
    periodicidad: str = "",
    desde: str = "",
    hasta: str = "",
    solo_proximas: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Search BCE's own statistical publication calendar -- scheduled release
    dates for IEM, Cuentas Nacionales, IMAEc, balance of payments, and more,
    each with its category, periodicity, reference period, and a direct
    link to the publication's page.

    Args:
        query: Free text matched (accent-insensitive) against the
            publication name or its observations note. Empty matches all.
        categoria: Exact category filter (accent-insensitive), e.g.
            "cuentas nacionales", "balanza de pagos y comercio exterior".
        periodicidad: Exact periodicity filter, e.g. "Mensual", "Anual",
            "Trimestral", "Semanal".
        desde: Restrict to fecha >= this date (YYYY-MM-DD).
        hasta: Restrict to fecha <= this date (YYYY-MM-DD).
        solo_proximas: If true, only entries whose fecha is today or later
            (ignores desde/hasta if also given, applying its own today-based
            lower bound in addition to hasta).
        limit: Max results (1-200, default 50).
        offset: Pagination offset over the matched set.
    """
    entries = await _fetch_calendario()
    q = _strip(query)
    cat = _strip(categoria)
    per = _strip(periodicidad)
    if solo_proximas:
        desde = desde or datetime.now(UTC).date().isoformat()

    def matches(entry: dict[str, Any]) -> bool:
        if q and q not in _strip(entry["nombre"]) and q not in _strip(entry["observaciones"]):
            return False
        if cat and cat != _strip(entry["categoria"]):
            return False
        if per and per != _strip(entry["periodicidad"]):
            return False
        if desde and entry["fecha"] < desde:
            return False
        return not (hasta and entry["fecha"] > hasta)

    matched = [entry for entry in entries if matches(entry)]
    cap = min(max(limit, 1), 200)
    offset = max(offset, 0)
    return {
        "source": _SOURCE_NAME,
        "url_fuente": _CSV_URL,
        "url_pagina": _PAGE_URL,
        "consultado_en": datetime.now(UTC).isoformat(),
        "total": len(matched),
        "total_calendario": len(entries),
        "offset": offset,
        "publicaciones": matched[offset : offset + cap],
    }

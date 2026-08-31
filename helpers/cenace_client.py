"""Client for CENACE's live grid-operations snapshot page
(cenace.gob.ec/info-operativa/InformacionOperativa.htm).

Confirmed 2026-08-30 by driving the page in a browser and watching the
network tab through all 5 tabs (Producción Tiempo Real, Demanda Tiempo
Real, Información Operativa Diaria, Acumulada Mensual, Acumulada Anual):
no AJAX/JSON call fires on tab switch. The whole page -- all 5 tabs'
numbers, including two Plotly-chart tabs and an SVG map -- is rendered
server-side into one ~260 KB HTML response; JS only toggles which
`<div class="tab-content">` is visible. So this is a plain scrape, no
reverse-engineered protocol needed.

Each of the 4 "producción" tabs has an identical `<div class="resumen">`
block of `<div class="resumen-box ...">` cards (label + value, thousands
separated with U+00A0 NBSP, not a regular space -- e.g. "97\xa0995").
The "demanda" tab's cards use different labels (DEMANDA TOTAL/ANTERIOR/
DEMANDA CNEL/EMPRESAS ELÉCTRICAS) but the same markup, so one generic
parser handles both rather than hardcoding two label sets. Per-distributor
demand (19 empresas eléctricas / CNEL entities) lives in the tab's SVG
choropleth map as `<title>NOMBRE&#10;NNN MW</title>` tags -- far simpler
to regex than correlating SVG path IDs to the equivalent Plotly bar chart
next to it, which encodes its values as base64-packed float64 arrays.

Deliberately NOT scraped: the per-plant/per-fuel-type breakdown (e.g.
"Coca Codo 39\xa0206 MWh") and the 24h generation curve, both only
available inside Plotly.newPlot(...) JSON blobs wrapped in a large
(15+ KB) shared color/theme template that would need careful stripping
to isolate the actual data array. The 6 resumen-box headline numbers per
tab plus the demand breakdown already cover the dashboard's real value
(live generation mix and demand); the chart-only detail can be added
later if an agent actually needs plant-level granularity.

This is a live snapshot, not a historical series: "Diaria" is yesterday's
full day, "Mensual"/"Anual" are month-to-date/year-to-date accumulators
as of today, and "Tiempo Real" is the current instant. There is no date
picker and no way to query a past day/month/year -- confirmed by the
absence of any such control in the page and by the lack of any API call
to fetch one. Every field returned here is only ever "as of now".
"""

from __future__ import annotations

import re
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes

_URL = "https://www.cenace.gob.ec/info-operativa/InformacionOperativa.htm"

# Numbers change continuously on the "tiempo real" tab; a short TTL keeps
# responses fresh without hammering the page on every tool call.
_cache = TtlCache(ttl_seconds=180.0, max_entries=1)

_H2_RE = re.compile(r"<h2>([^<]+)</h2>")
_PERIOD_RE = re.compile(r"</header>\s*<div[^>]*>\s*<span>([^<]+)</span>")
_RESUMEN_BOX_RE = re.compile(r'<div class="resumen-box \w+"><div>([^<]+)</div><div>([^<]+)</div></div>')
_DISTRIBUIDORA_RE = re.compile(r"<title>([^&<]+)&#10;([\d\s\xa0]+) MW</title>")

_TABS = {
    "produccion_tiempo_real": "PRODUCCIÓN EN TIEMPO REAL",
    "demanda_tiempo_real": "DEMANDAS EMPRESAS ELÉCTRICAS DE DISTRIBUCIÓN",
    "operativa_diaria": "INFORMACIÓN OPERATIVA DIARIA",
    "acumulada_mensual": "INFORMACIÓN OPERATIVA MENSUAL",
    "acumulada_anual": "INFORMACIÓN OPERATIVA ANUAL",
}


def _to_number(raw: str) -> float:
    cleaned = raw.replace("\xa0", "").replace(" ", "").strip()
    return float(cleaned) if "." in cleaned else int(cleaned)


def _split_sections(html: str) -> dict[str, str]:
    matches = list(_H2_RE.finditer(html))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        sections[m.group(1)] = html[start:end]
    return sections


async def _fetch_sections() -> dict[str, str]:
    cached = _cache.get("sections")
    if cached is not None:
        return cached
    content, truncated = await download_bytes(_URL)
    if truncated:
        raise ValueError("La página de CENACE superó el límite de descarga.")
    html = content.decode("utf-8", errors="replace")
    sections = _split_sections(html)
    _cache.set("sections", sections)
    return sections


def list_tableros() -> list[str]:
    """The fixed set of tablero (tab) names accepted by get_tablero."""
    return list(_TABS)


async def get_tablero(tablero: str) -> dict[str, Any]:
    """
    Fetch one tablero (tab) of CENACE's live grid-operations snapshot.

    Args:
        tablero: One of list_tableros() -- produccion_tiempo_real,
            demanda_tiempo_real, operativa_diaria, acumulada_mensual,
            acumulada_anual.

    Returns headline resumen numbers (production/demand totals by
    category, unit MWh for the daily tabs and GWh for the annual one)
    plus, for demanda_tiempo_real, a per-distributor MW breakdown. Always
    an as-of-now snapshot -- see module docstring for why there is no
    historical query here.
    """
    if tablero not in _TABS:
        raise ValueError(f"Tablero '{tablero}' no reconocido. Válidos: {', '.join(_TABS)}")

    sections = await _fetch_sections()
    h2_title = _TABS[tablero]
    block = sections.get(h2_title)
    if block is None:
        raise ValueError(f"No se encontró la sección '{h2_title}' en la página de CENACE.")

    period_match = _PERIOD_RE.search(block)
    resumen = {label.strip(): _to_number(value) for label, value in _RESUMEN_BOX_RE.findall(block)}

    result: dict[str, Any] = {
        "tablero": tablero,
        "titulo": h2_title,
        "periodo": period_match.group(1).strip() if period_match else None,
        "resumen": resumen,
    }
    if tablero == "demanda_tiempo_real":
        result["por_distribuidora_mw"] = {
            name.strip(): _to_number(mw) for name, mw in _DISTRIBUIDORA_RE.findall(block)
        }
    return result

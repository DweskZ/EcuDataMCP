"""Client for SIPA's (sipa.agricultura.gob.ec) "Resumen de Indicadores"
monthly report — one of the sub-pages hanging off the "Indicadores
Sectoriales" tablero dinámico page
(sipa-estadisticas/tablero-dinamico/indicadores-sectoriales).

Investigation context (2026-09-03, live-verified): "Indicadores
Sectoriales" itself is a landing page with three icon links — "Indicador
Agroeconómico" (/index.php/indicador-agroeconomico), "Indicador
Agrosocial" (/index.php/indicador-agrosocial), and "Resumen de
Indicadores" (/index.php/resumen-de-indicadores/<year>) — plus a default
embedded dashboard. The first two, and the page's own default embed, are
genuine **Tableau Server** dashboards (not Power BI): the iframe target
(https://servicios.mag.gob.ec/tableros/<workbook>/<view>) resolves to a
small HTML shim that loads
https://bi.mag.gob.ec/javascripts/api/tableau.embedding.3.latest.js and
points a <tableau-viz> at https://bi.mag.gob.ec/views/<workbook>/<view>
using a long-lived signed JWT ("Connected App" token, `scp:
tableau:views:embed`). Reproducing this would mean reverse-engineering
Tableau's embedding/REST protocol against a self-hosted bi.mag.gob.ec
server — a distinct, much bigger effort than this client, out of scope
here (see helpers/sut_powerbi_client.py for what that class of effort
looks like for Power BI; this is the Tableau equivalent, unbuilt).
Separately, the site-wide "Informes" nav (Panorama Agroeconómico, Atlas
Agroeconómico, Hoja de Balance de Alimentos, Índice de Productividad) and
"Informe de Rendimientos Objetivos" (rice) are each trapped in a
fliphtml5.com JS flipbook with an opaque encoded book config — confirmed
dead end, no direct PDF/XLSX link found for any of them (matches the
already-documented Panorama Agroeconómico finding in RESEARCH.md; now
confirmed live for the other three too). The rice "Rendimientos
Objetivos" page additionally embeds a per-year Tableau dashboard
(bi.mag.gob.ec/views/ORO_prod_<YY>_arroz/c_producc) behind its year links
— none of those "year" links (2014-2025) lead to a distinct page; they
all resolve back to the same listing with a different year's dashboard
embedded.

"Resumen de Indicadores" is the one exception: a genuine, static,
Joomla-rendered listing of direct monthly PDF links — same
`?download=`-free pattern as helpers/sipa_client.py and
helpers/bce_remesas_client.py. Confirmed live 2018-2026. Each year is a
separate Joomla article/URL
(/index.php/resumen-de-indicadores[/<year>], where 2018 — the first
year published — lives at the bare URL with no year suffix, everything
2019+ has an explicit /<year> segment) rather than one page listing every
year, so this client fetches one year at a time. The on-page filename
convention isn't stable across years either (2018:
`indicadores-<mm>-18.pdf`, 2019+: `indicadores_<mes-en-español>_<yyyy>.pdf`)
— confirmed by direct comparison, not assumed — so URLs are always taken
verbatim from the scraped href, never constructed from the year/month
alone. Each year page also carries a hand-maintained "Año 2018 / Año
2019 / ..." nav paragraph that is not reliably current (the 2018 page's
copy of this paragraph was missing "Año 2026" at verification time, while
the 2026 page's copy had the full 2018-2026 range) — this client surfaces
whatever list it finds on the page it fetched as `anios_disponibles`, but
that's a hint for exploration, not an authoritative index; it deliberately
doesn't hardcode "the current year" anywhere.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urljoin

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://sipa.agricultura.gob.ec"
_PAGE_PATH = "/index.php/resumen-de-indicadores"

# First year with a published "Resumen de Indicadores" page, confirmed live —
# it lives at the bare _PAGE_PATH with no /<year> suffix (Joomla quirk: this
# was the first article created, before the later ones adopted a /<year>
# segment).
ANIO_MINIMO = 2018

# One year's page rarely changes after the fact (only the current year gains
# a new month a few times a year); max_entries is generous rather than tied
# to a fixed year count, since new years keep getting added.
_page_cache = TtlCache(ttl_seconds=21600.0, max_entries=64)
_fetch_lock = asyncio.Lock()

_ITEM_SPLIT_RE = re.compile(r'<div class="el-item uk-panel">')
_LINK_RE = re.compile(r'<a\s+href="(?P<url>[^"]+\.pdf)"[^>]*>(?P<mes>[^<]+)</a>', re.IGNORECASE)
_YEAR_NAV_RE = re.compile(
    r'<a\s+href="(?P<href>/index\.php/resumen-de-indicadores(?:/(?P<yr>\d{4}))?)"\s*>'
    r"\s*Año\s*(?P<label>\d{4})"
)


def _year_url(anio: int) -> str:
    if anio == ANIO_MINIMO:
        return f"{_BASE}{_PAGE_PATH}"
    return f"{_BASE}{_PAGE_PATH}/{anio}"


def _parse_meses(html: str) -> list[dict[str, str]]:
    meses = []
    for chunk in _ITEM_SPLIT_RE.split(html)[1:]:
        link_m = _LINK_RE.search(chunk)
        if link_m is None:
            continue
        url = urljoin(_BASE, link_m.group("url"))
        meses.append(
            {
                "mes": link_m.group("mes").strip(),
                "url": url,
                "formato": "PDF",
            }
        )
    return meses


def _parse_anios_disponibles(html: str) -> list[int]:
    anios = set()
    for m in _YEAR_NAV_RE.finditer(html):
        # A bare-URL nav entry (no /<year> suffix) always points at
        # ANIO_MINIMO; every other entry's URL segment and label agree in
        # every page checked live, but the label is the more direct source
        # of truth for "which year is this link for" so it wins.
        anios.add(int(m.group("label")))
    return sorted(anios)


async def get_resumen_indicadores(anio: int) -> dict[str, Any]:
    """
    Fetch one year of SIPA's "Resumen de Indicadores" page and list its
    monthly direct PDF download links.

    Args:
        anio: Year, e.g. 2025. Earliest confirmed live: ANIO_MINIMO (2018).
    """
    if anio < ANIO_MINIMO:
        raise ValueError(
            f"Año {anio} no soportado. El primer año publicado es {ANIO_MINIMO}."
        )

    cached = _page_cache.get(anio)
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _page_cache.get(anio)
        if cached is not None:
            return cached

        url = _year_url(anio)
        logger.info("Descargando la página de Resumen de Indicadores SIPA: %s", url)
        content, truncated = await download_bytes(url)
        if truncated:
            raise ValueError(f"La página de {url} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        meses = _parse_meses(html)
        anios_disponibles = _parse_anios_disponibles(html)
        result = {
            "anio": anio,
            "url": url,
            "meses": meses,
            "anios_disponibles": anios_disponibles,
        }
        if meses:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/sipa_client.py / helpers/contraloria_client.py — an
            # empty result is indistinguishable from a transient failure, or
            # (for the current year before its first month is published) not
            # yet real content, and should self-correct on the next call
            # instead of being pinned for the full TTL.
            _page_cache.set(anio, result)
        return result

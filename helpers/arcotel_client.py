"""Client for ARCOTEL's (Agencia de Regulación y Control de las
Telecomunicaciones — www.arcotel.gob.ec) two institutional-site PDF series:
"Reportes Estadísticos Mensuales" and "Boletín Estadístico del Sector de
las Telecomunicaciones". Both live outside CKAN — ARCOTEL's CKAN
organization (`arcotel`, 9 CSV/ODS datasets) is frozen since Nov 2021/2022
and not covered here; see RESEARCH.md's "CNT / ARCOTEL" entry for that
comparison.

Confirmed live 2026-09-02 (today per the environment). Both pages:
  - Are plain static HTML — no JS/accordion rendering needed, every year's
    links are already in the DOM (WordPress theme "Sitio-32", not a
    download-monitor site like helpers/cnig_client.py's).
  - Serve a nested `<ul id="menu-menu_lateral_institucion">` sidebar menu:
    one `<li>` per year (label taken from a broken-but-consistent
    `<a href="http://Junio">YYYY</a>` anchor — a real CMS quirk, not a
    scraping artifact) containing a nested `<ul>` of direct `.pdf` links.
  - Need `curl --ssl-no-revoke` / a client that skips OCSP revocation
    checking to reach at all from this environment (Windows schannel
    raised CRYPT_E_NO_REVOCATION_CHECK on a bare `curl`) — but that's a
    local TLS-stack quirk, not a portal-side block: no login/CAPTCHA, and
    `helpers.csv_reader.download_bytes` (httpx, not schannel) reaches it
    fine.
  - Every sampled PDF resolves directly (HTTP 200, `Content-Type:
    application/pdf`, `Accept-Ranges: bytes`), sizes in the low single-digit
    MB — well under this project's 5 MB preview cap, but these are listed
    as links only (no CSV/XLSX structured data exists), not parsed here.

Reportes Estadísticos Mensuales (`/reportes-estadisticos-mensuales/`):
monthly reports, confirmed live range January 2017 (as "Infografía N —
..." topical PDFs, before the series settled into one-PDF-per-month) through
June 2026 — the most recent upload (`6.-Junio-2026.pdf`, `Last-Modified:
2026-08-31`) lags today by about 2 months, not the ~4 months noted in prior
research; either the lag has since narrowed or that prior estimate ran
against an earlier snapshot — flagged as a discrepancy rather than
silently overwritten. The 2023-2026 window is exactly one row (month) per
PDF; 2017-2022 mixes months and ad hoc infographic topics.

Boletín Estadístico (`/boletines-estadisticos/`, `/boletin-estadistico/`
redirects here): annual/topical statistical bulletins, confirmed live range
2015 through 2024 — a different, lower-frequency, more topic-driven series
(e.g. "Servicio Portador — Agosto", "Roaming-Nacional Automático") than the
one-per-month Reportes. No 2025/2026 bulletin yet as of this check.

Both pages share the exact same markup shape, so one parser
(`_parse_entries`) serves both fetch functions; results carry a `anio`
field derived from the nearest preceding year header in document order,
since (unlike helpers/cnig_client.py's flat, unlabeled entries) year is
useful, directly-usable context here and costs nothing extra to keep.

A handful of very old (2017-2019) entries render as two separate `<a>`
tags pointing at the same PDF with split label text (e.g. "Infografía3-"
then "STF: (abr2017)" as two anchors) — this parser dedupes by URL and
keeps the first label only, same as every other URL-keyed scraper in this
project (helpers/cnig_client.py, helpers/bce_remesas_client.py); a few
old, non-primary entries losing half their label is an acceptable
trade-off against the complexity of merging adjacent anchors.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_MENSUALES_URL = "https://www.arcotel.gob.ec/reportes-estadisticos-mensuales/"
_BOLETINES_URL = "https://www.arcotel.gob.ec/boletines-estadisticos/"

# Reports land roughly monthly with a multi-month lag (see module
# docstring) -- a few hours just avoids re-scraping the page on every call,
# same rationale/value as helpers/cnig_client.py and
# helpers/bce_remesas_client.py.
_mensuales_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_boletines_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

# The CMS's own (broken) year-header anchor -- every year `<li>` on both
# pages opens with this exact literal `href="http://Junio"`, confirmed live
# across both pages; it's a more reliable anchor than the surrounding
# `menu-item-19031` id, which is reused verbatim for every year.
_YEAR_RE = re.compile(r'<a href="http://Junio">(\d{4})</a>')
_LINK_RE = re.compile(r'<a\s+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub("", text))).strip()


def _parse_entries(page_html: str) -> list[dict[str, str]]:
    years = [(m.start(), m.group(1)) for m in _YEAR_RE.finditer(page_html)]
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    year_idx = 0
    current_year = ""
    for m in _LINK_RE.finditer(page_html):
        pos = m.start()
        while year_idx < len(years) and years[year_idx][0] <= pos:
            current_year = years[year_idx][1]
            year_idx += 1
        url = m.group(1)
        if not url.startswith("http"):
            continue
        if url in seen:
            continue
        seen.add(url)
        label = _clean(m.group(2))
        if not label:
            continue
        entries.append(
            {"anio": current_year, "label": label, "url": url, "format": "PDF"}
        )
    return entries


async def _fetch(url: str, cache: TtlCache, label: str) -> list[dict[str, str]]:
    cached = cache.get("entries")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = cache.get("entries")
        if cached is not None:
            return cached

        logger.info("Descargando la página de %s de ARCOTEL (%s)", label, url)
        content, truncated = await download_bytes(url)
        if truncated:
            raise ValueError(f"La página de {url} superó el límite de descarga.")
        page_html = content.decode("utf-8", errors="replace")

        entries = _parse_entries(page_html)
        if entries:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/cnig_client.py / helpers/bce_remesas_client.py.
            cache.set("entries", entries)
        return entries


def _search(entries: list[dict[str, str]], query: str) -> list[dict[str, str]]:
    q = _strip(query)
    if not q:
        return entries
    return [
        e
        for e in entries
        if q in _strip(e["label"]) or q in _strip(e["anio"]) or q in _strip(e["url"])
    ]


async def search_reportes_mensuales(query: str = "") -> dict[str, Any]:
    """
    List (optionally filtered) ARCOTEL Reportes Estadísticos Mensuales PDFs.

    Args:
        query: Free text matched (accent-insensitive) against the entry's
            label, year, or URL, e.g. "junio 2026", "2025", "internet".
            Empty returns all entries.
    """
    entries = await _fetch(_MENSUALES_URL, _mensuales_cache, "Reportes Estadísticos Mensuales")
    matched = _search(entries, query)
    return {
        "total": len(matched),
        "total_en_pagina": len(entries),
        "source": "ARCOTEL — Reportes Estadísticos Mensuales",
        "url_fuente": _MENSUALES_URL,
        "archivos": matched,
    }


async def search_boletines_estadisticos(query: str = "") -> dict[str, Any]:
    """
    List (optionally filtered) ARCOTEL Boletín Estadístico del Sector de
    las Telecomunicaciones PDFs.

    Args:
        query: Free text matched (accent-insensitive) against the entry's
            label, year, or URL, e.g. "roaming", "2020", "portabilidad".
            Empty returns all entries.
    """
    entries = await _fetch(_BOLETINES_URL, _boletines_cache, "Boletines Estadísticos")
    matched = _search(entries, query)
    return {
        "total": len(matched),
        "total_en_pagina": len(entries),
        "source": "ARCOTEL — Boletín Estadístico del Sector de las Telecomunicaciones",
        "url_fuente": _BOLETINES_URL,
        "archivos": matched,
    }

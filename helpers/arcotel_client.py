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


# -- statistical series (XLSX) -------------------------------------------------

# ARCOTEL's statistics tree (/estadisticas-de-telecomunicaciones2/ and its
# per-service pages) links ~3,000 XLSX/XLS uploads, named
# "{código}-{Indicador}_{mes}_{año}[_F|_V2].xlsx" (1.1.1 líneas activas,
# 1.2 radiobases, 1.3.1 portabilidad, 2.1.1 telefonía fija, 3.1.1 cuentas de
# internet, 4.1.1 TV pagada, 8.1.x concesiones de radio y TV, 14.1 reclamos,
# ...). Each monthly file carries the series' whole history (1.1.1 from 2008,
# 3.1.1 from 2010, checked 2026-11-07), so the newest file per code is the
# series. The WordPress media API lists them newest first, which is easier
# than walking three levels of pages.
_MEDIA_URL = "https://www.arcotel.gob.ec/wp-json/wp/v2/media"
_SERIES_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
)
# Ten pages of 100 reach back past every series' latest upload (the slowest,
# yearly ones included) without paging all ~4,000 files.
_SERIES_PAGES = 10
_CODE_RE = re.compile(r"^(\d+(?:[.-]\d+)*)\.?[-_]")
_NAMED_SERIES = {"informe_series_tel_fija": "Informe series de telefonía fija", "indice_de_valor_agregado_parroquial": "Índice de Valor Agregado Parroquial (IVAP)"}
_MONTH_TOKENS = {
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "setiembre", "octubre", "noviembre", "diciembre",
    "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic", "mes",
}
_series_cache = TtlCache(ttl_seconds=21600.0, max_entries=1, persist="arcotel_series")
_SERIES_CODE_RE = re.compile(r"\d{1,2}(\.\d{1,2}){1,2}")
_NOT_SERIES_RE = re.compile(r"observacion|formulario|formato|matriz|copy|reforma|analisis")


def series_key(filename: str) -> tuple[str, str] | None:
    """(code, readable name) of an ARCOTEL statistics file, or None."""
    stem = filename.rsplit(".", 1)[0]
    match = _CODE_RE.match(stem)
    if match:
        code = match.group(1).replace("-", ".").strip(".")
        rest = stem[match.end():]
    else:
        lowered = stem.lower().replace("-", "_")
        named = next((k for k in _NAMED_SERIES if lowered.startswith(k)), None)
        if named is None:
            return None
        return named, _NAMED_SERIES[named]
    words = []
    for token in re.split(r"[-_\s]+", rest):
        low = _strip(token)
        if not token or low in _MONTH_TOKENS or re.fullmatch(r"(19|20)\d\d|v\d+|f|\d{1,2}|\d{6,8}", low):
            if low in _MONTH_TOKENS or re.fullmatch(r"(19|20)\d\d", low):
                break
            continue
        words.append(token)
    return code, " ".join(words) or code


def parse_series_media(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest file per series code, with how many uploads were seen."""
    series: dict[str, dict[str, Any]] = {}
    for item in sorted(items, key=lambda i: i.get("date") or "", reverse=True):
        url = item.get("source_url") or ""
        key = series_key(url.rsplit("/", 1)[-1])
        if key is None:
            continue
        code, name = key
        # Real series codes are 1-2 digit groups ("1.1.1", "14.1"); the same
        # media library holds consultation forms ("Formulario observaciones",
        # "Matriz ...") that also start with numbers.
        if code[0].isdigit() and (
            not _SERIES_CODE_RE.fullmatch(code) or _NOT_SERIES_RE.search(_strip(name))
        ):
            continue
        if code in series:
            series[code]["versiones_vistas"] += 1
            continue
        series[code] = {
            "codigo": code,
            "titulo": f"{code} {name}" if code[0].isdigit() else name,
            "url": url,
            "formato": url.rsplit(".", 1)[-1].upper(),
            "fecha": str(item.get("date") or "")[:10],
            "versiones_vistas": 1,
        }

    def order(entry: dict[str, Any]) -> list[Any]:
        return [int(p) if p.isdigit() else p for p in re.split(r"[.]", entry["codigo"])]

    return sorted(series.values(), key=lambda e: (not e["codigo"][0].isdigit(), order(e)))


async def _fetch_series_fresh() -> list[dict[str, Any]]:
    cached = _series_cache.get("series")
    if cached is not None:
        return cached
    import json as _json
    from urllib.parse import urlencode

    async def page(mime: str, n: int) -> list[dict[str, Any]]:
        query = urlencode(
            {"mime_type": mime, "per_page": 100, "page": n, "_fields": "date,source_url"}
        )
        raw, truncated = await download_bytes(f"{_MEDIA_URL}?{query}", raise_for_status=frozenset({400}))
        if truncated:
            raise ValueError("La API de medios de ARCOTEL superó el límite de descarga.")
        data = _json.loads(raw.decode("utf-8", errors="replace"))
        return data if isinstance(data, list) else []  # 400 past the last page

    pages = await asyncio.gather(
        *(page(_SERIES_MIME[0], n) for n in range(1, _SERIES_PAGES + 1)),
        *(page(_SERIES_MIME[1], n) for n in range(1, 4)),
    )
    series = parse_series_media([item for p in pages for item in p])
    if series:
        _series_cache.set("series", series)
    return series


async def _fetch_series() -> list[dict[str, Any]]:
    """Fresh fetch, or the last good copy when the source fails (see TtlCache.serve_stale)."""
    try:
        return await _fetch_series_fresh()
    except Exception as exc:
        stale = _series_cache.serve_stale("series", exc)
        if stale is None:
            raise
        return stale


async def search_series_estadisticas(query: str = "") -> dict[str, Any]:
    """Latest XLSX of each ARCOTEL statistical series, filtered by text."""
    series = await _fetch_series()
    q = _strip(query)
    matched = [s for s in series if not q or q in _strip(f"{s['codigo']} {s['titulo']}")]
    return {
        "source": "ARCOTEL — series estadísticas de telecomunicaciones (XLSX)",
        "url_fuente": "https://www.arcotel.gob.ec/estadisticas-de-telecomunicaciones2/",
        "nota": (
            "Un archivo por serie, el más reciente: cada XLSX trae la historia completa "
            "(líneas activas desde 2008, cuentas de internet desde 2010). Ábrelo con "
            "preview_resource_data o download_resource."
        ),
        "archivos": matched,
    }

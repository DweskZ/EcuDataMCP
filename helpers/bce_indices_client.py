"""Client for BCE's site-wide "índice" archive pages — a WordPress plugin
(`sistema-gestion-editorial-bce`, its own "gestor de índices") that BCE uses
to publish year-by-year (or week-by-week) file archives for ~35 named
series: sector bulletins (petroleum, mining, cement), trade price indices,
EMOE/confidence indices, FX buy/sell, balance of payments, remittances,
weekly monetary bulletins, and more. Confirmed live 2026-09-01: every page
whose slug ends in "-indice"/"-indices" (found via the site's own
`wp-sitemap-posts-page-1.xml`) renders one of two static widgets, fully
present in the initial HTML -- no AJAX, no admin-ajax round trip needed:

- `.bce-gi` (annual/quarterly/monthly cadence): a year-tab bar plus one
  `.bce-gi-panel` per year, each holding `.bce-gi-card` entries (one per
  period) with a period label, a direct file link, and a format tag.
- `.bce-gi-weekly` (weekly cadence, e.g. the weekly monetary bulletin):
  year cards, each expanding to month groups of `.bce-gi-weekly-link`
  entries (week number + Spanish long-form date + direct file link).

Not a duplicate of BCEData/IEM (helpers/bce_client.py,
helpers/bce_iem_client.py): these are named published documents (PDF/XLSX/
HTML reports), most with no equivalent numeric series in either. May
overlap in *topic* with helpers/bce_remesas_client.py (there is a
"Boletín Analítico de Evolución de las Remesas" índice page) -- that is a
different artifact (an analytical bulletin, not the raw remittance series
BCEData/bce_remesas_client already expose) and is left as a separate,
distinctly-named catalog entry rather than merged.

Because building the catalog means fetching every discovered page once
(there is no lighter-weight index of titles), the catalog itself caches
the fully parsed archive per page -- `search_indices` returns summaries
only (to keep responses agent-sized); `get_archivo` reads the already-
cached items for one page, no second fetch needed.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://contenido.bce.fin.ec"
_SITEMAP_URL = f"{_BASE}/wp-sitemap-posts-page-1.xml"
_SOURCE_NAME = "Banco Central del Ecuador — Índices de publicaciones"

# The set of "-indice" pages themselves changes rarely (new pages are added
# a few times a year); the content within each (new periods) changes as
# often as weekly. 6h matches the TTL other publication-list clients in
# this project use (helpers/bce_publicaciones_client.py, sri_client.py).
_PAGE_FETCH_CONCURRENCY = 6
_catalog_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_WS_RE = re.compile(r"\s+")
_SITEMAP_ENTRY_RE = re.compile(
    r"<url><loc>(?P<url>[^<]+)</loc><lastmod>(?P<lastmod>[^<]+)</lastmod></url>"
)
_INDICE_SLUG_RE = re.compile(r"-indices?(?:-\d+)?/?$", re.IGNORECASE)

_GI_ROOT_RE = re.compile(r'<section class="(?P<classes>bce-gi(?:\s[\w-]+)?)"', re.IGNORECASE)
_GI_WEEKLY_ROOT_RE = re.compile(r'<section class="bce-gi-weekly"[^>]*aria-label="(?P<titulo>[^"]*)"')
_GI_TITLE_RE = re.compile(r'<div class="bce-gi-title">.*?<h2>(?P<titulo>.*?)</h2>', re.DOTALL)
_GI_PANEL_RE = re.compile(
    r'<div class="bce-gi-panel[^"]*" data-year="(?P<anio>\d+)"\s*>(?P<body>.*?)'
    # "bce-gi-panel" is also a prefix of "bce-gi-panelhead" (the summary div
    # inside each panel's own body) -- the lookahead must require a quote or
    # space right after "panel", or it stops at the panel's own head instead
    # of the next year's panel.
    r'(?=<div class="bce-gi-panel(?:"|\s)|\Z)',
    re.DOTALL,
)
_GI_CARD_RE = re.compile(r'<article class="bce-gi-card[^"]*">(?P<body>.*?)</article>', re.DOTALL)
_CARD_HREF_RE = re.compile(r'<a[^>]*href="(?P<href>[^"]+)"')
_CARD_LABEL_RE = re.compile(r"<strong>(?P<label>.*?)</strong>", re.DOTALL)
_CARD_DESC_RE = re.compile(r'<p class="bce-gi-month-desc">(?P<desc>.*?)</p>', re.DOTALL)
_CARD_TAGS_RE = re.compile(r'<div class="bce-gi-tags">(?P<body>.*?)</div>', re.DOTALL)
_TAG_SPAN_RE = re.compile(r"<span>(?P<tag>.*?)</span>", re.DOTALL)

_GI_WEEKLY_TITLE_RE = re.compile(
    r'<h2 class="bce-gi-weekly-title">(?P<titulo>.*?)</h2>', re.DOTALL
)
_GI_WEEKLY_PANEL_RE = re.compile(
    # A non-active panel carries a trailing `hidden` attribute instead of a
    # bare closing `>` (confirmed live: only the current year's panel omits
    # it) -- match any attributes between the year and the tag close.
    r'<section class="bce-gi-weekly-panel" data-year="(?P<anio>\d+)"[^>]*>(?P<body>.*?)'
    r'(?=<section class="bce-gi-weekly-panel|\Z)',
    re.DOTALL,
)
_GI_WEEKLY_LINK_RE = re.compile(
    r'<a class="bce-gi-weekly-link"[^>]*href="(?P<href>[^"]+)"[^>]*>'
    r'.*?<span class="week-nro">(?P<nro>.*?)</span>'
    r'.*?<span class="week-date">(?P<fecha>.*?)</span>',
    re.DOTALL,
)
_FECHA_TEXTO_RE = re.compile(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", re.IGNORECASE)

_MESES_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

_FORMATOS_POR_EXTENSION = {
    "pdf": "PDF",
    "xlsx": "XLSX",
    "xls": "XLS",
    "csv": "CSV",
    "zip": "ZIP",
    "html": "HTML",
    "htm": "HTML",
}


def _clean_text(html_fragment: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", html_fragment)
    return _WS_RE.sub(" ", without_tags).strip()


def _parse_fecha(texto: str) -> str | None:
    """"9 de enero de 2026" -> "2026-01-09"; None if unrecognized."""
    m = _FECHA_TEXTO_RE.search(texto)
    if not m:
        return None
    dia, mes_texto, anio = m.groups()
    mes = _MESES_ES.get(_strip(mes_texto))
    if mes is None:
        return None
    return f"{int(anio):04d}-{mes:02d}-{int(dia):02d}"


def _formato_from_url(url: str) -> str:
    path = urlsplit(url).path
    if "." not in path.rsplit("/", 1)[-1]:
        return "DESCONOCIDO"
    ext = path.rsplit(".", 1)[-1].lower()
    return _FORMATOS_POR_EXTENSION.get(ext, ext.upper())


def _absolute(href: str) -> str:
    return href if href.startswith("http") else urljoin(_BASE, href)


def _parse_gi_cards(html: str) -> tuple[str, str, list[dict[str, Any]]]:
    """Parse a `.bce-gi` (year-tabs) widget. Returns (titulo, cadencia, items)."""
    root_m = _GI_ROOT_RE.search(html)
    cadencia = ""
    if root_m:
        classes = root_m.group("classes").split()
        cadencia = next((c[len("bce-gi-") :] for c in classes if c.startswith("bce-gi-")), "")
    title_m = _GI_TITLE_RE.search(html)
    titulo = _clean_text(title_m.group("titulo")) if title_m else ""

    items: list[dict[str, Any]] = []
    for panel_m in _GI_PANEL_RE.finditer(html):
        anio = int(panel_m.group("anio"))
        for card_m in _GI_CARD_RE.finditer(panel_m.group("body")):
            body = card_m.group("body")
            href_m = _CARD_HREF_RE.search(body)
            label_m = _CARD_LABEL_RE.search(body)
            if not href_m or not label_m:
                continue
            desc_m = _CARD_DESC_RE.search(body)
            tags_m = _CARD_TAGS_RE.search(body)
            formatos = (
                [_clean_text(t) for t in _TAG_SPAN_RE.findall(tags_m.group("body"))]
                if tags_m
                else []
            )
            url = _absolute(href_m.group("href"))
            items.append(
                {
                    "anio": anio,
                    "periodo": _clean_text(label_m.group("label")),
                    "descripcion": _clean_text(desc_m.group("desc")) if desc_m else None,
                    "fecha": None,
                    "fecha_texto": None,
                    "url": url,
                    "formato": "/".join(formatos) if formatos else _formato_from_url(url),
                }
            )
    return titulo, cadencia, items


def _parse_gi_weekly(html: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse a `.bce-gi-weekly` widget. Returns (titulo, items)."""
    title_m = _GI_WEEKLY_TITLE_RE.search(html)
    if title_m:
        titulo = _clean_text(title_m.group("titulo"))
    else:
        root_m = _GI_WEEKLY_ROOT_RE.search(html)
        titulo = _clean_text(root_m.group("titulo")) if root_m else ""

    items: list[dict[str, Any]] = []
    for panel_m in _GI_WEEKLY_PANEL_RE.finditer(html):
        anio = int(panel_m.group("anio"))
        for link_m in _GI_WEEKLY_LINK_RE.finditer(panel_m.group("body")):
            fecha_texto = _clean_text(link_m.group("fecha"))
            url = _absolute(link_m.group("href"))
            items.append(
                {
                    "anio": anio,
                    "periodo": _clean_text(link_m.group("nro")),
                    "descripcion": None,
                    "fecha": _parse_fecha(fecha_texto),
                    "fecha_texto": fecha_texto,
                    "url": url,
                    "formato": _formato_from_url(url),
                }
            )
    return titulo, items


def _parse_pagina(url: str, html: str) -> dict[str, Any] | None:
    """Parse one índice page. Returns None if it carries neither known widget
    (a false positive from the sitemap's slug-based filter)."""
    if _GI_WEEKLY_TITLE_RE.search(html) or _GI_WEEKLY_ROOT_RE.search(html):
        titulo, items = _parse_gi_weekly(html)
        cadencia = "semanal"
    elif _GI_ROOT_RE.search(html):
        titulo, cadencia, items = _parse_gi_cards(html)
    else:
        return None

    anios = [item["anio"] for item in items]
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return {
        "pagina_id": slug,
        "titulo": titulo or slug,
        "url": url,
        "cadencia": cadencia or None,
        "total_archivos": len(items),
        "rango_anios": [min(anios), max(anios)] if anios else None,
        "archivos": items,
    }


async def _discover_paginas() -> list[dict[str, str]]:
    content, truncated = await download_bytes(_SITEMAP_URL)
    if truncated:
        raise ValueError(f"El sitemap de {_SITEMAP_URL} superó el límite de descarga.")
    xml = content.decode("utf-8", errors="replace")
    return [
        {"url": m.group("url"), "lastmod": m.group("lastmod")}
        for m in _SITEMAP_ENTRY_RE.finditer(xml)
        if _INDICE_SLUG_RE.search(m.group("url"))
    ]


async def _fetch_catalog() -> list[dict[str, Any]]:
    cached = _catalog_cache.get("catalog")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _catalog_cache.get("catalog")
        if cached is not None:
            return cached

        logger.info("Descubriendo páginas de índices de publicaciones del BCE")
        candidatos = await _discover_paginas()
        semaphore = asyncio.Semaphore(_PAGE_FETCH_CONCURRENCY)

        async def fetch_one(candidato: dict[str, str]) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    content, truncated = await download_bytes(candidato["url"])
                    if truncated:
                        return None
                    html = content.decode("utf-8", errors="replace")
                    parsed = _parse_pagina(candidato["url"], html)
                    if parsed is not None:
                        parsed["actualizado_sitemap"] = candidato["lastmod"]
                    return parsed
                except Exception as exc:
                    logger.warning(
                        "No se pudo leer la página de índice %s: %s", candidato["url"], exc
                    )
                    return None

        results = await asyncio.gather(*(fetch_one(c) for c in candidatos))
        catalog = [entry for entry in results if entry is not None]
        if catalog:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/bce_remesas_client.py and helpers/bce_publicaciones_client.py.
            _catalog_cache.set("catalog", catalog)
        return catalog


def clear_cache() -> None:
    """Clear the índices catalog cache; useful for refresh jobs and tests."""
    _catalog_cache.clear()


def _resumen(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "archivos"}


async def search_indices(query: str = "") -> dict[str, Any]:
    """
    List (optionally filtered) BCE "índice" archive pages — one per named
    publication series (sector bulletins, trade price indices, EMOE/
    confidence indices, FX buy/sell, balance of payments, weekly monetary
    bulletins, etc.), each with a year-by-year or week-by-week file archive.

    Returns summaries only (title, page URL, cadence, year range, file
    count) — call get_bce_indice_archivo with the returned pagina_id to read
    the actual file list for one page.

    Args:
        query: Free text matched (accent-insensitive) against the page's
            title or URL. Empty returns all discovered pages.
    """
    catalog = await _fetch_catalog()
    q = _strip(query)
    matched = [
        entry
        for entry in catalog
        if not q or q in _strip(entry["titulo"]) or q in _strip(entry["url"])
    ]
    return {
        "total": len(matched),
        "total_paginas": len(catalog),
        "source": _SOURCE_NAME,
        "paginas": [_resumen(entry) for entry in matched],
    }


_MAX_ARCHIVOS = 200
_DEFAULT_MAX_ARCHIVOS = 30


async def get_archivo(pagina_id: str, anio: int = 0, max_archivos: int = _DEFAULT_MAX_ARCHIVOS) -> dict[str, Any]:
    """
    Read the file archive for one BCE "índice" page (from search_bce_indices).

    Args:
        pagina_id: The page's slug, from search_bce_indices' `pagina_id`
            field (e.g. "boletin-analitico-del-sector-petrolero-indice").
        anio: Restrict to one calendar year. 0 returns all years found.
        max_archivos: Cap on returned files (most recent years first),
            1-200. Use `anio` to reach further back than the cap allows.
    """
    catalog = await _fetch_catalog()
    entry = next((e for e in catalog if e["pagina_id"] == pagina_id.strip()), None)
    if entry is None:
        raise ValueError(f"Página de índice '{pagina_id}' no encontrada")

    archivos = entry["archivos"]
    if anio:
        archivos = [item for item in archivos if item["anio"] == anio]
    cap = min(max(max_archivos, 1), _MAX_ARCHIVOS)
    limitado = archivos[:cap]
    return {
        "source": _SOURCE_NAME,
        "pagina": _resumen(entry),
        "total_archivos": len(archivos),
        "archivos_mostrados": len(limitado),
        "truncado": len(archivos) > len(limitado),
        "archivos": limitado,
    }

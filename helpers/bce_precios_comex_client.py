"""Client for BCE's disaggregated foreign-trade price-index pages --
`indices-de-precios-de-importacion` and `indices-de-precios-de-exportacion`
(contenido.bce.fin.ec) -- confirmed live 2026-09-02 to be genuinely distinct
from data this project already exposes elsewhere:

- BCEData (helpers/bce_client.py, id_grupo 134 "Índices IPX - IPM - ITI")
  only has three *aggregate* monthly series: general export price index,
  general import price index, and the terms-of-trade index (ITI).
- helpers/bce_indices_client.py's ~35 "índice" archive pages (the
  `.bce-gi`/`.bce-gi-weekly` year-tab widget, discovered via the site's own
  sitemap) don't cover trade prices at all -- these two pages' slugs don't
  end in "-indice"/"-indices" so the sitemap-based discovery never finds
  them, and even if it did, they render a third, structurally different
  widget (see below), not `.bce-gi`.

The two XLSX files these pages link to hold genuinely new detail: import
prices broken down by economic-use category (fuels/lubricants, raw
materials, consumer goods, capital goods, "diversos") and export prices
broken down by individual product (crude oil, shrimp, banana, cacao,
copper, gold, roses, broccoli, pitahaya, ...), each with separate
price/value/volume sheets and monthly/annual/cumulative variation sheets --
none of which exist in BCEData's id_grupo 134 or anywhere else in this
project's BCE integrations (confirmed: search_indicadores_bce has zero
results for "banano precio", "petroleo precio", "bienes de capital
indice"). That's the fully live-verified basis for building this client.

A third, sibling page --
`serie-historica-indices-de-precios-comercio-exterior-y-terminos-de-intercambio`
-- was investigated and deliberately excluded. Its XLSX (IPX/IPM/ITI
sheets, one column each) carries the exact same three aggregate series
already in BCEData id_grupo 134 (cross-checked live: ITI Jun 2026 =
90.2604172608485 in both, IPX Jun 2026 = 106.592212310699 vs
106.5922123106989 -- same value, float-precision noise only). Integrating
it would be a pure duplicate in a slightly different shape, exactly what
this project's BCE integrations deliberately avoid.

Confirmed live: unlike bce_indices_client's `.bce-gi` pages (a year-tab
archive of many historical files) these two pages use a much simpler,
different widget -- a single static `<ul class="bce-download-list">`
linking to ONE continuously-updated XLSX per page (BCE republishes the same
file in place; there is no year-by-year archive to page through). That
schema mismatch (no per-item year) is why this isn't folded into
bce_indices_client's `.bce-gi` parser/known-pages list -- its return shape
assumes an `anio` per item for `rango_anios`, which does not apply here.
Instead this follows helpers/bce_remesas_client.py's shape: a flat list of
current file links (label/url/format), no archive-by-year. The two page
URLs are hardcoded (same rationale as `_EXTRA_TOPICS` in
helpers/inec_client.py: a small, hand-verified set outside normal
discovery) while each page's actual file link(s) are scraped live, in case
BCE ever renames the file or adds a second one to a page.

Reading the category-level series inside the XLSX itself is left to the
caller (download the returned URL) -- this project's generic
preview_resource_data/query_resource_data tools are CKAN-resource-scoped
and don't apply to a raw BCE URL, the same limitation already accepted for
bce_indices_client and bce_remesas_client.
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
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://contenido.bce.fin.ec"
_SOURCE_NAME = "Banco Central del Ecuador — Índices de Precios de Comercio Exterior"

# Hand-verified set, outside the sitemap-based discovery bce_indices_client
# uses (these slugs don't end in "-indice"/"-indices") -- same rationale as
# _EXTRA_TOPICS in helpers/inec_client.py. Deliberately excludes the
# sibling "serie-historica-..." page: see module docstring, it's a pure
# duplicate of BCEData id_grupo 134.
_PAGINAS = (
    {
        "pagina_id": "indices-de-precios-de-importacion",
        "titulo": "Índice de Precios de Importaciones por Uso o Destino Económico",
        "url": f"{_BASE}/indices-de-precios-de-importacion/",
    },
    {
        "pagina_id": "indices-de-precios-de-exportacion",
        "titulo": "Índice de Precios de Exportaciones por Grupos de Productos",
        "url": f"{_BASE}/indices-de-precios-de-exportacion/",
    },
)

# Same TTL rationale as bce_remesas_client/bce_indices_client: the file
# itself is republished in place roughly monthly, the page structure
# changes rarely.
_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_DOWNLOAD_LIST_RE = re.compile(r'<ul class="bce-download-list">(?P<body>.*?)</ul>', re.DOTALL)
_LINK_RE = re.compile(r'<a[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<label>.*?)</a>', re.DOTALL)
_WS_RE = re.compile(r"\s+")

_FORMATOS_POR_EXTENSION = {
    "pdf": "PDF",
    "xlsx": "XLSX",
    "xls": "XLS",
    "csv": "CSV",
    "zip": "ZIP",
}


def _clean_text(fragment: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", fragment)
    return _WS_RE.sub(" ", without_tags).strip()


def _absolute(href: str) -> str:
    return href if href.startswith("http") else urljoin(_BASE, href)


def _formato_from_url(url: str) -> str:
    name = url.rsplit("/", 1)[-1]
    if "." not in name:
        return "DESCONOCIDO"
    ext = name.rsplit(".", 1)[-1].lower()
    return _FORMATOS_POR_EXTENSION.get(ext, ext.upper())


def _parse_download_list(html: str) -> list[dict[str, str]]:
    """Parse a `.bce-download-list` widget -- a flat `<ul>` of file links,
    no archive-by-year (see module docstring)."""
    list_m = _DOWNLOAD_LIST_RE.search(html)
    if not list_m:
        return []
    archivos: list[dict[str, str]] = []
    seen: set[str] = set()
    for link_m in _LINK_RE.finditer(list_m.group("body")):
        url = _absolute(link_m.group("href"))
        if url in seen:
            continue
        seen.add(url)
        archivos.append(
            {
                "label": _clean_text(link_m.group("label")),
                "url": url,
                "format": _formato_from_url(url),
            }
        )
    return archivos


async def _fetch_pagina(pagina: dict[str, str]) -> list[dict[str, str]]:
    try:
        content, truncated = await download_bytes(pagina["url"])
        if truncated:
            logger.warning(
                "La página de precios de comercio exterior %s superó el límite de descarga",
                pagina["url"],
            )
            return []
        html = content.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning(
            "No se pudo leer la página de precios de comercio exterior %s: %s",
            pagina["url"],
            exc,
        )
        return []

    return [
        {
            "pagina_id": pagina["pagina_id"],
            "pagina_titulo": pagina["titulo"],
            "url_pagina": pagina["url"],
            **archivo,
        }
        for archivo in _parse_download_list(html)
    ]


async def _fetch_files() -> list[dict[str, str]]:
    cached = _files_cache.get("files")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _files_cache.get("files")
        if cached is not None:
            return cached

        logger.info("Descargando páginas de índices de precios de comercio exterior del BCE")
        results = await asyncio.gather(*(_fetch_pagina(p) for p in _PAGINAS))
        files = [archivo for pagina_files in results for archivo in pagina_files]
        if files:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/bce_remesas_client.py and helpers/bce_indices_client.py.
            _files_cache.set("files", files)
        return files


def clear_cache() -> None:
    """Clear the índices de precios de comercio exterior cache; useful for
    refresh jobs and tests."""
    _files_cache.clear()


async def search_archivos(query: str = "") -> dict[str, Any]:
    """
    List BCE's disaggregated foreign-trade price-index file links --
    import prices by economic-use category and export prices by product,
    each with price/value/volume and variation detail (see module
    docstring for why this is distinct from BCEData's aggregate IPX/IPM/ITI
    series).

    Args:
        query: Free text matched (accent-insensitive) against the file's
            label, its page title, or its page id. Empty returns all files.
    """
    files = await _fetch_files()
    q = _strip(query)
    matched = [
        f
        for f in files
        if not q
        or q in _strip(f["label"])
        or q in _strip(f["pagina_titulo"])
        or q in _strip(f["pagina_id"])
    ]
    return {
        "total": len(matched),
        "total_en_paginas": len(files),
        "source": _SOURCE_NAME,
        "paginas": [dict(p) for p in _PAGINAS],
        "archivos": matched,
    }

"""Client for BCE's "Últimas Publicaciones" feed
(contenido.bce.fin.ec/ultimas-publicaciones/) — a catalog of the BCE's
periodic reports/bulletins (PDF/XLSX/interactive HTML pages), not a
duplicate of BCEData (helpers/bce_client.py) or IEM
(helpers/bce_iem_client.py): neither exposes these named publications with
their publication date and direct file link, and most of what shows up
here (weekly monetary bulletins, analytical bulletins, interactive rate
reports) has no equivalent numeric series in either.

Confirmed live: the page renders a single static HTML `<table>` (via a
`bce-ultimas-publicaciones` shortcode, server-rendered — no AJAX, no
`wp-json` route backs it) listing the ~30 most recent publications, newest
first. There is no pagination and no date-range parameter on the page
itself, so this client can only see that rolling window, not a full
historical archive -- same caveat as helpers/bce_indicadores_diarios_client
has for its widget snapshots.

Each row carries a publication date (Spanish long form, e.g. "1 de
septiembre de 2026"), a title, and a link. The page also renders a format
icon per row (dashicons class + title, e.g. "file-pdf" / "Documento PDF"),
but the icon is an editorial choice (a couple of interactive-report rows
use a generic "chart" icon instead of the real file type) -- the URL's own
extension is the reliable source for `formato`, per the same
don't-trust-the-declared-type rule CLAUDE.md documents for CKAN's `format`
field. The icon title is kept as `icono_titulo` for reference only.
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

_PAGE_URL = "https://contenido.bce.fin.ec/ultimas-publicaciones/"
_BASE = "https://contenido.bce.fin.ec"
_SOURCE_NAME = "Banco Central del Ecuador — Últimas Publicaciones"

# The page is hand-updated multiple times a week; 6h matches the TTL other
# list-scraping clients in this project use for similar publication feeds
# (helpers/sri_client.py, helpers/inec_client.py, helpers/bce_remesas_client.py).
_publicaciones_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_WS_RE = re.compile(r"\s+")
_SECTION_RE = re.compile(
    r'<section class="bce-ultimas-publicaciones">.*?</section>', re.DOTALL
)
_ROW_RE = re.compile(r"<tr>(?P<row>.*?)</tr>", re.DOTALL)
_FECHA_RE = re.compile(r'<td class="fecha">(?P<fecha>.*?)</td>', re.DOTALL)
_ICONO_RE = re.compile(
    r'<td class="icono"><span class="(?P<classes>[^"]*)"(?:\s+title="(?P<titulo>[^"]*)")?',
    re.DOTALL,
)
_LINK_RE = re.compile(
    r'<td class="publicacion"><a[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<titulo>.*?)</a>',
    re.DOTALL,
)
_NUEVO_RE = re.compile(r'<td class="nuevo">.*?class="(?P<classes>[^"]*)"', re.DOTALL)
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


def _parse_fecha(texto: str) -> str | None:
    """"1 de septiembre de 2026" -> "2026-09-01"; None if unrecognized."""
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


def _parse_publicaciones(html: str) -> list[dict[str, Any]]:
    section_match = _SECTION_RE.search(html)
    scoped = section_match.group(0) if section_match else html

    items: list[dict[str, Any]] = []
    for row_match in _ROW_RE.finditer(scoped):
        row = row_match.group("row")
        fecha_m = _FECHA_RE.search(row)
        link_m = _LINK_RE.search(row)
        if not fecha_m or not link_m:
            continue  # header row, or a shape this scrape doesn't recognize

        href = link_m.group("href")
        url = href if href.startswith("http") else urljoin(_BASE, href)
        fecha_texto = _WS_RE.sub(" ", fecha_m.group("fecha")).strip()
        icono_m = _ICONO_RE.search(row)
        nuevo_m = _NUEVO_RE.search(row)

        items.append(
            {
                "fecha": _parse_fecha(fecha_texto),
                "fecha_texto": fecha_texto,
                "titulo": _WS_RE.sub(" ", link_m.group("titulo")).strip(),
                "url": url,
                "formato": _formato_from_url(url),
                "icono_titulo": icono_m.group("titulo") if icono_m else None,
                "nuevo": bool(nuevo_m)
                and "icono-vacio" not in nuevo_m.group("classes"),
            }
        )
    return items


async def _fetch_publicaciones() -> list[dict[str, Any]]:
    cached = _publicaciones_cache.get("publicaciones")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _publicaciones_cache.get("publicaciones")
        if cached is not None:
            return cached

        logger.info("Descargando la página de Últimas Publicaciones del BCE")
        content, truncated = await download_bytes(_PAGE_URL)
        if truncated:
            raise ValueError(f"La página de {_PAGE_URL} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        items = _parse_publicaciones(html)
        if items:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/contraloria_client.py and helpers/bce_remesas_client.py.
            _publicaciones_cache.set("publicaciones", items)
        return items


def clear_cache() -> None:
    """Clear the publications cache; useful for refresh jobs and tests."""
    _publicaciones_cache.clear()


async def search_publicaciones(query: str = "", formato: str = "") -> dict[str, Any]:
    """
    List (optionally filtered) recent BCE publications from "Últimas Publicaciones".

    Only the rolling window the page itself exposes (currently the ~30 most
    recent entries, newest first) -- there is no server-side pagination or
    date-range filter to reach further back.

    Args:
        query: Free text matched (accent-insensitive) against the
            publication's title. Empty returns all.
        formato: Exact match (case-insensitive) against the derived format
            (PDF, XLSX, XLS, CSV, ZIP, HTML). Empty returns all formats.
    """
    items = await _fetch_publicaciones()
    q = _strip(query)
    fmt = formato.strip().upper()
    matched = [
        item
        for item in items
        if (not q or q in _strip(item["titulo"]))
        and (not fmt or item["formato"] == fmt)
    ]
    return {
        "total": len(matched),
        "total_en_pagina": len(items),
        "source": _SOURCE_NAME,
        "url_fuente": _PAGE_URL,
        "publicaciones": matched,
    }

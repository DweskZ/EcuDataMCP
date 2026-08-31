"""Clients for two SRI pages that publish direct file links outside the CKAN
portal's DataStore:

- **Datasets** (https://www.sri.gob.ec/datasets, `search_files`) — ~130
  CSV/XLSX/ZIP files: RUC catastro by province, recaudación by year,
  ventas/compras, vehículos nuevos, comprobantes electrónicos (CEL), plus
  variable dictionaries. A Liferay CMS layout: each file link sits inside a
  <p> next to a short label (e.g. "SRI_Recaudación_2026 - 7,8 Mb"). The page
  also groups files into named sections (data-analytics-asset-title, e.g.
  "Catastro RUC por provincia"), but at least one section is mislabeled
  ("Prueba" — Spanish for "Test" — actually holds the real "Recaudación"
  yearly files), so that grouping isn't reliable enough to expose; only the
  per-file label and URL are extracted here, which is what a keyword search
  actually needs.
- **Estadísticas de Recaudación**
  (https://www.sri.gob.ec/estadisticas-generales-de-recaudacion-sri,
  `search_estadisticas_recaudacion`) — a different aggregation level than
  /datasets' raw yearly declaration exports: XLSX reports pre-aggregated by
  impuesto/provincia/cantón and by actividad económica, updated monthly,
  plus a historical-indicators ZIP, an annual PDF boletín técnico, and
  infografías. Links live in a Liferay "Biblioteca Alfresco" document
  library (`/o/sri-portlet-biblioteca-alfresco-internet/descargar/<uuid>/
  <filename>`) rather than the /datasets page's `<p>`-wrapped layout, so the
  label is derived from the URL's filename (which already carries the
  report name and month/year, e.g. "Recaudación por impuesto provincia y
  cantón_julio2026.xlsx") instead of surrounding HTML text.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import unquote

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.tls import should_retry_insecure
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

SRI_DATASETS_URL = "https://www.sri.gob.ec/datasets"
SRI_ESTADISTICAS_URL = "https://www.sri.gob.ec/estadisticas-generales-de-recaudacion-sri"
_DOWNLOAD_TIMEOUT = 30.0

# The page is hand-maintained and rarely changes within a day; a few hours
# balances staleness against re-fetching/re-parsing ~260 KB of HTML.
_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
# Guards the cache-miss path so concurrent callers don't each independently
# fetch+parse the page.
_fetch_lock = asyncio.Lock()

_FILE_LINK_RE = re.compile(
    r'<p>((?:(?!</p>).)*?<a\s+[^>]*href="([^"]+\.(?:csv|xlsx|xls|zip))"[^>]*>[^<]*</a>(?:(?!</p>).)*?)</p>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# The monthly recaudación reports live in a Liferay "Biblioteca Alfresco"
# document library, a different layout than /datasets' <p>-wrapped links --
# matched by host path rather than trailing extension so a future added
# format on that same library still gets picked up.
_ALFRESCO_LINK_RE = re.compile(
    r'href="(https://www\.sri\.gob\.ec/o/sri-portlet-biblioteca-alfresco-internet/'
    r'descargar/[^"]+\.(?:xlsx|xls|csv|zip|pdf))"',
    re.IGNORECASE,
)

# Updated monthly (verified live for the July 2026 edition); a few hours
# balances staleness against re-fetching the page, same rationale as
# _files_cache above.
_estadisticas_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_estadisticas_fetch_lock = asyncio.Lock()


def _clean_label(fragment: str, url: str) -> str:
    text = fragment.replace(url, "")
    text = _TAG_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ")
    text = _WS_RE.sub(" ", text).strip(" -")
    for noise in ("Descargar", "descargar"):
        text = text.replace(noise, "").strip(" -")
    return text


def _parse_files(html: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for m in _FILE_LINK_RE.finditer(html):
        fragment, url = m.group(1), m.group(2)
        label = _clean_label(fragment, url)
        fmt = url.rsplit(".", 1)[-1].upper()
        files.append({"label": label or url.rsplit("/", 1)[-1], "url": url, "format": fmt})
    return files


async def _download_page(url: str, verify: bool = True) -> str:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=_DOWNLOAD_TIMEOUT,
        verify=verify,
    ) as session:
        resp = await session.get(url)
        resp.raise_for_status()
        return resp.text


async def _fetch_files() -> list[dict[str, str]]:
    cached = _files_cache.get("files")
    if cached is not None:
        return cached

    async with _fetch_lock:
        # Another coroutine may have populated the cache while this one was
        # waiting for the lock; re-check before fetching again.
        cached = _files_cache.get("files")
        if cached is not None:
            return cached

        logger.info("Descargando la página de datasets del SRI")
        try:
            html = await _download_page(SRI_DATASETS_URL)
        except httpx.ConnectError as exc:
            if not should_retry_insecure(exc, SRI_DATASETS_URL):
                raise
            logger.warning(
                "Falló la verificación TLS para %s; reintentando sin verificación",
                SRI_DATASETS_URL,
            )
            html = await _download_page(SRI_DATASETS_URL, verify=False)

        files = _parse_files(html)
        _files_cache.set("files", files)
        logger.info("Página de datasets del SRI cargada: %d archivos", len(files))
        return files


async def search_files(query: str = "", limit: int = 30, offset: int = 0) -> dict[str, Any]:
    """
    Search the SRI open datasets page's direct file links client-side.

    Args:
        query: Free text matched (accent-insensitive) against the file's
            label or URL. Empty returns all files.
        limit: Max results returned.
        offset: Pagination offset over the matched set.
    """
    files = await _fetch_files()
    q = _strip(query)

    matched = [
        f for f in files if not q or q in _strip(f["label"]) or q in _strip(f["url"])
    ]
    page = matched[offset : offset + limit]
    return {
        "total": len(matched),
        "total_en_pagina": len(files),
        "offset": offset,
        "source": "SRI — Datasets abiertos",
        "url_fuente": SRI_DATASETS_URL,
        "archivos": page,
    }


def _label_from_url(url: str) -> str:
    """Derive a human label from an Alfresco download URL's filename.

    The page's anchor text is a generic call-to-action ("Ver estadísticas de
    recaudación"), not a real label -- the actual report name and
    month/year live only in the filename (e.g. "Recaudación por impuesto
    provincia y cantón_julio2026.xlsx").
    """
    filename = unquote(url.rsplit("/", 1)[-1])
    stem = filename.rsplit(".", 1)[0]
    return _WS_RE.sub(" ", stem.replace("_", " ")).strip()


def _parse_estadisticas_files(html: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in _ALFRESCO_LINK_RE.finditer(html):
        url = m.group(1)
        if url in seen:
            continue
        seen.add(url)
        fmt = url.rsplit(".", 1)[-1].upper()
        files.append({"label": _label_from_url(url), "url": url, "format": fmt})
    return files


async def _fetch_estadisticas_files() -> list[dict[str, str]]:
    cached = _estadisticas_cache.get("files")
    if cached is not None:
        return cached

    async with _estadisticas_fetch_lock:
        cached = _estadisticas_cache.get("files")
        if cached is not None:
            return cached

        logger.info("Descargando la página de Estadísticas de Recaudación del SRI")
        try:
            html = await _download_page(SRI_ESTADISTICAS_URL)
        except httpx.ConnectError as exc:
            if not should_retry_insecure(exc, SRI_ESTADISTICAS_URL):
                raise
            logger.warning(
                "Falló la verificación TLS para %s; reintentando sin verificación",
                SRI_ESTADISTICAS_URL,
            )
            html = await _download_page(SRI_ESTADISTICAS_URL, verify=False)

        files = _parse_estadisticas_files(html)
        _estadisticas_cache.set("files", files)
        logger.info(
            "Página de Estadísticas de Recaudación del SRI cargada: %d archivos",
            len(files),
        )
        return files


async def search_estadisticas_recaudacion(
    query: str = "", limit: int = 30, offset: int = 0
) -> dict[str, Any]:
    """
    Search the SRI's "Estadísticas de Recaudación" page for direct file links.

    A different aggregation level than search_files' raw yearly exports:
    monthly XLSX reports of recaudación by impuesto/provincia/cantón and by
    actividad económica, updated monthly, plus a ZIP of historical
    indicators, an annual PDF boletín técnico, and infografías.

    Args:
        query: Free text matched (accent-insensitive) against the file's
            label or URL. Empty returns all files.
        limit: Max results returned.
        offset: Pagination offset over the matched set.
    """
    files = await _fetch_estadisticas_files()
    q = _strip(query)

    matched = [
        f for f in files if not q or q in _strip(f["label"]) or q in _strip(f["url"])
    ]
    page = matched[offset : offset + limit]
    return {
        "total": len(matched),
        "total_en_pagina": len(files),
        "offset": offset,
        "source": "SRI — Estadísticas de Recaudación",
        "url_fuente": SRI_ESTADISTICAS_URL,
        "archivos": page,
    }

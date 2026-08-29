"""Client for the SRI open datasets page (https://www.sri.gob.ec/datasets).

The SRI publishes ~130 direct download links (CSV/XLSX/ZIP) plus variable
dictionaries on a single stable HTML page — it isn't in the CKAN portal's
DataStore, so those files aren't reachable through search_datasets. The page
is a Liferay CMS layout, not an API: each file link sits inside a <p> next to
a short label (e.g. "SRI_Recaudación_2026 - 7,8 Mb"). The page also groups
files into named sections (data-analytics-asset-title, e.g. "Catastro RUC por
provincia"), but at least one section is mislabeled ("Prueba" — Spanish for
"Test" — actually holds the real "Recaudación" yearly files), so that
grouping isn't reliable enough to expose; only the per-file label and URL are
extracted here, which is what a keyword search actually needs.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.tls import should_retry_insecure
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

SRI_DATASETS_URL = "https://www.sri.gob.ec/datasets"
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


async def _download_page(verify: bool = True) -> str:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=_DOWNLOAD_TIMEOUT,
        verify=verify,
    ) as session:
        resp = await session.get(SRI_DATASETS_URL)
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
            html = await _download_page()
        except httpx.ConnectError as exc:
            if not should_retry_insecure(exc, SRI_DATASETS_URL):
                raise
            logger.warning(
                "Falló la verificación TLS para %s; reintentando sin verificación",
                SRI_DATASETS_URL,
            )
            html = await _download_page(verify=False)

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

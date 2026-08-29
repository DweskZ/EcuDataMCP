"""Client for INEC's statistical-topic pages (ecuadorencifras.gob.ec).

Each topic (IPC, ENEMDU, ENSANUT, pobreza, comercio exterior...) has its own
plain WordPress page listing its latest technical bulletin, methodology, and
historical series as direct file links (PDF/XLSX/CSV/ZIP) — no JS involved,
confirmed live. This is INEC's aggregate/published-indicator layer: it covers
content ANDA's microdata catalog (`helpers/anda_client.py`) structurally
cannot (index-type operations like IPC show up in ANDA as metadata-only
stubs with no downloadable microdata).

There is no site search or sitemap for the topic list, but every topic page
embeds the same site-wide nav menu (a "mega-menu" with ~75 entries, one per
topic, each linking to that topic's page). `_seed page` below is used only to
read that shared menu — nothing about it is special beyond being confirmed
live and stable. The bare domain root (`/`) and the `/estadisticas/` path
are NOT usable for this: `/` serves a `W3 Total Cache`-cached meta-refresh
shell last generated 2021-06-16, and `/estadisticas/` serves an unrelated
legacy Liferay-era shell — both dead ends confirmed live, see RESEARCH.md.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any
from unicodedata import category, normalize

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.tls import should_retry_insecure
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

# Any live topic page works as the menu source; IPC is a flagship, unlikely
# to be renamed or retired.
_SEED_PAGE_URL = "https://www.ecuadorencifras.gob.ec/indice-de-precios-al-consumidor/"
_SITE_PREFIX = "https://www.ecuadorencifras.gob.ec/"
_DOWNLOAD_TIMEOUT = 30.0

# Topic list changes only when INEC restructures its nav (rare); topic pages
# themselves are refreshed with new bulletins roughly monthly.
_topics_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_topic_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=128)
_fetch_lock = asyncio.Lock()

_TOPIC_LINK_RE = re.compile(
    r'<a class="mega-menu-link" href="(https://www\.ecuadorencifras\.gob\.ec/[^"]+)">'
    r"([^<]+)</a>"
)
_FILE_LINK_RE = re.compile(
    r'href="(https://www\.ecuadorencifras\.gob\.ec/documentos/'
    r'[^"]+\.(pdf|xlsx|xls|csv|zip|docx?))"',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _strip_accents(text: str) -> str:
    nfkd = normalize("NFKD", text or "")
    return "".join(c for c in nfkd if category(c) != "Mn").lower()


def _label_from_url(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    name = name.rsplit(".", 1)[0]
    return name.replace("_", " ").replace("-", " ").strip()


async def _get_page(url: str, verify: bool = True) -> str:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=_DOWNLOAD_TIMEOUT,
        verify=verify,
    ) as session:
        resp = await session.get(url)
        resp.raise_for_status()
        return resp.text


async def _fetch_page_with_tls_fallback(url: str) -> str:
    try:
        return await _get_page(url)
    except httpx.ConnectError as exc:
        if not should_retry_insecure(exc, url):
            raise
        logger.warning("Falló la verificación TLS para %s; reintentando sin verificación", url)
        return await _get_page(url, verify=False)


def _parse_topics(html: str) -> list[dict[str, str]]:
    seen: dict[str, str] = {}
    for url, name in _TOPIC_LINK_RE.findall(html):
        # A handful of menu entries point at legacy static micrositios
        # (documentos/web-inec/Sitios/...) instead of a topic page; they have
        # no file listing to scrape, but are harmless to keep discoverable.
        seen.setdefault(url, unescape(name).strip())
    return [{"nombre": name, "url": url} for url, name in seen.items()]


async def _fetch_topics() -> list[dict[str, str]]:
    cached = _topics_cache.get("topics")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _topics_cache.get("topics")
        if cached is not None:
            return cached

        logger.info("Descargando el menú de temas de Ecuador en Cifras (INEC)")
        html = await _fetch_page_with_tls_fallback(_SEED_PAGE_URL)
        topics = _parse_topics(html)
        _topics_cache.set("topics", topics)
        logger.info("Menú de temas de Ecuador en Cifras cargado: %d temas", len(topics))
        return topics


async def search_topics(query: str = "", limit: int = 30, offset: int = 0) -> dict[str, Any]:
    """
    Search INEC's statistical topic menu (ecuadorencifras.gob.ec) client-side.

    Args:
        query: Free text matched (accent-insensitive) against the topic name.
            Empty returns all topics.
        limit: Max results returned.
        offset: Pagination offset over the matched set.
    """
    topics = await _fetch_topics()
    q = _strip_accents(query)

    matched = [t for t in topics if not q or q in _strip_accents(t["nombre"])]
    page = matched[offset : offset + limit]
    return {
        "total": len(matched),
        "total_temas": len(topics),
        "offset": offset,
        "temas": page,
    }


def _parse_topic_files(html: str, topic_url: str) -> dict[str, Any]:
    title_match = _TITLE_RE.search(html)
    title = unescape(title_match.group(1)).strip(" |") if title_match else topic_url

    seen: dict[str, str] = {}
    for url, ext in _FILE_LINK_RE.findall(html):
        seen.setdefault(url, ext.upper())

    files = [
        {"label": _label_from_url(url), "url": url, "format": fmt} for url, fmt in seen.items()
    ]
    return {"titulo": title, "url": topic_url, "archivos": files}


async def get_topic_files(topic_url: str) -> dict[str, Any]:
    """
    Fetch one topic page and extract its direct file links.

    Args:
        topic_url: A topic URL from search_topics's "url" field. Must be on
            ecuadorencifras.gob.ec.
    """
    if not topic_url.startswith(_SITE_PREFIX):
        raise ValueError(f"URL fuera de ecuadorencifras.gob.ec: {topic_url}")

    cached = _topic_files_cache.get(topic_url)
    if cached is not None:
        return cached

    html = await _fetch_page_with_tls_fallback(topic_url)
    result = _parse_topic_files(html, topic_url)
    _topic_files_cache.set(topic_url, result)
    return result

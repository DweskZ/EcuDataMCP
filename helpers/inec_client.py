"""Client for INEC's Ecuador en Cifras site (ecuadorencifras.gob.ec).

Two independent discovery layers, kept separate because they cover
different things and neither subsumes the other:

1. **Topic pages** (`search_topics`/`get_topic_files`, the original layer).
   Each topic (IPC, ENEMDU, ENSANUT, pobreza, comercio exterior...) has its
   own plain WordPress page listing its latest technical bulletin,
   methodology, and historical series as direct file links
   (PDF/XLSX/CSV/ZIP) -- no JS involved, confirmed live. The topic list is
   scraped from the site's nav menu, which turns out to NOT be identical on
   every page (confirmed live: the menu on `estadisticas-laborales-enemdu/`
   has ~109 entries including `enemdu-anual/`/`enemdu-trimestral/` that
   never appear in the menu on the IPC seed page) -- so multiple seed pages
   are merged to reduce, not eliminate, that gap. Some topic pages are also
   themselves stale (a page can go years without a new file being linked
   from it, even while INEC keeps publishing that same topic -- see layer 2
   below), see RESEARCH.md § Novena pasada for the audit that found this.

2. **Publications via the WordPress REST API**
   (`search_publicaciones`/`get_publicacion_files`, layer 2). INEC's
   monthly/quarterly/annual bulletins are WordPress *posts*, not page edits,
   and the site exposes the public, unauthenticated core WP REST API at
   `/wp-json/wp/v2/`. This is authoritative and always current (confirmed
   live: 1,707 posts total, newest within days of being checked) --
   `/institucional/noticias/` and `/institucional/boletines/` are just
   category-filtered HTML views of this same collection, not a separate
   source. Prefer this layer for "what's the latest X" questions; prefer
   topic pages for "what operations does INEC even run" browsing, since the
   REST API has no single query that reconstructs the curated topic
   taxonomy (WP categories are broad subject buckets like "Economía
   Laboral", not one category per statistical operation).

This is INEC's aggregate/published-indicator layer overall: it covers
content ANDA's microdata catalog (`helpers/anda_client.py`) structurally
cannot (index-type operations like IPC show up in ANDA as metadata-only
stubs with no downloadable microdata).

The bare domain root (`/`) and the `/estadisticas/` path are NOT usable as
topic-menu seeds: `/` serves a `W3 Total Cache`-cached meta-refresh shell
last generated 2021-06-16, and `/estadisticas/` serves an unrelated legacy
Liferay-era shell -- both dead ends confirmed live, see RESEARCH.md.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any

import httpx

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip_accents

logger = logging.getLogger(MAIN_LOGGER_NAME)

# Two seed pages, not one: confirmed live that the site's nav menu differs
# by page, so a single seed misses real topics (e.g. the ENEMDU-specific
# pages only appear in the menu on an employment-related page, never on the
# IPC one). Merged and deduped in _fetch_topics.
_SEED_PAGE_URLS = (
    "https://www.ecuadorencifras.gob.ec/indice-de-precios-al-consumidor/",
    "https://www.ecuadorencifras.gob.ec/estadisticas-laborales-enemdu/",
)

# Confirmed-real pages that aren't reachable from either seed page's menu at
# all (same "menu isn't the same on every page" gap the seeds above exist to
# reduce) -- added by hand as they're found rather than hunting for a third
# seed page every time. The geoportal micrositio hosts the official
# Clasificador Geográfico Estadístico (DPA codes/shapefiles) for every year
# 2001-2026; confirmed live it has no menu entry pointing to it anywhere.
_EXTRA_TOPICS = (
    {
        "nombre": "Geoportal / Clasificador Geográfico Estadístico (DPA)",
        "url": (
            "https://www.ecuadorencifras.gob.ec/documentos/web-inec/"
            "Geografia_Estadistica/Micrositio_geoportal/index.html"
        ),
    },
)
_SITE_PREFIX = "https://www.ecuadorencifras.gob.ec/"
_API_BASE = "https://www.ecuadorencifras.gob.ec/wp-json/wp/v2"

# Topic list changes only when INEC restructures its nav (rare); topic pages
# themselves are refreshed with new bulletins roughly monthly.
_topics_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_topic_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=128)
_categories_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_publicacion_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=256)
_fetch_lock = asyncio.Lock()

_TOPIC_LINK_RE = re.compile(
    r'<a class="mega-menu-link" href="(https://www\.ecuadorencifras\.gob\.ec/[^"]+)">'
    r"([^<]+)</a>"
)
# Top-level mega-menu entries can have dropdown children that use a
# different markup shape (a plain <a>, no mega-menu-link class, wrapped in
# an <li class="menu-item ...">) -- confirmed live: this is how ENEMDU's
# anual/trimestral/telefonica sub-pages are actually linked, missed by
# _TOPIC_LINK_RE alone.
_SUBMENU_LINK_RE = re.compile(
    r'<li[^>]*class="menu-item[^"]*"[^>]*>\s*'
    r'<a(?:\s+title="[^"]*")?\s+href="(https://www\.ecuadorencifras\.gob\.ec/[^"]+)">'
    r"([^<]+)"
)
_FILE_LINK_RE = re.compile(
    # Confirmed live on the Geografia_Estadistica micrositio: some real
    # links have a doubled slash (".ec//documentos/...") that browsers/
    # servers normalize but a literal single "/" here would miss entirely.
    r'href="(https://www\.ecuadorencifras\.gob\.ec/+documentos/'
    r'[^"]+\.(pdf|xlsx|xls|csv|zip|docx?))"',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _label_from_url(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    name = name.rsplit(".", 1)[0]
    return name.replace("_", " ").replace("-", " ").strip()


async def _get_page(url: str) -> str:
    # download_bytes is SSRF-guarded (validates the URL and every redirect
    # hop resolve to a public IP) and already retries insecurely on the
    # shared TLS-fallback allowlist -- needed here because get_topic_files
    # takes a URL from the model, not just the hardcoded seed page constant.
    content, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(f"La página en {url} superó el límite de descarga.")
    return content.decode("utf-8", errors="replace")


def _parse_topics(html: str) -> list[dict[str, str]]:
    seen: dict[str, str] = {}
    for url, name in _TOPIC_LINK_RE.findall(html) + _SUBMENU_LINK_RE.findall(html):
        # A handful of menu entries point at legacy static micrositios
        # (documentos/web-inec/Sitios/...) or directly at a PDF/XLSX instead
        # of a topic page; they have no further file listing to scrape (or
        # already are the file), but are harmless to keep discoverable.
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
        pages = await asyncio.gather(
            *(_get_page(url) for url in _SEED_PAGE_URLS), return_exceptions=True
        )
        seen: dict[str, str] = {}
        loaded = 0
        for url, page in zip(_SEED_PAGE_URLS, pages, strict=True):
            if isinstance(page, BaseException):
                logger.warning("No se pudo cargar el menú desde %s: %s", url, page)
                continue
            loaded += 1
            for topic in _parse_topics(page):
                seen.setdefault(topic["url"], topic["nombre"])
        if not loaded:
            raise ValueError("No se pudo cargar el menú de temas de Ecuador en Cifras")
        for topic in _EXTRA_TOPICS:
            seen.setdefault(topic["url"], topic["nombre"])

        topics = [{"nombre": name, "url": url} for url, name in seen.items()]
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

    html = await _get_page(topic_url)
    result = _parse_topic_files(html, topic_url)
    _topic_files_cache.set(topic_url, result)
    return result


# -- WordPress REST API layer -------------------------------------------
#
# _API_BASE is a hardcoded, first-party-configured host (never derived from
# model/user input), same trust level as helpers.bce_client's _BASE_URL --
# plain httpx is used here rather than the SSRF-guarded download_bytes,
# matching that precedent, and because header access (X-WP-Total) is needed
# for honest pagination totals.


async def _get_api_json(
    path: str, params: dict[str, Any], session: httpx.AsyncClient | None = None
) -> tuple[Any, httpx.Headers]:
    own = session is None
    if own:
        session = httpx.AsyncClient(timeout=25.0)
    assert session is not None
    try:
        resp = await session.get(f"{_API_BASE}/{path}", params=params)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message")
            except Exception:
                detail = None
            raise ValueError(
                detail or f"La API de Ecuador en Cifras devolvió HTTP {resp.status_code}"
            )
        return resp.json(), resp.headers
    finally:
        if own:
            await session.aclose()


async def _fetch_categories() -> dict[int, str]:
    """id -> name map for every WordPress category, fetched once and cached.

    These are broad subject buckets (e.g. "Economía Laboral" holds both
    ENEMDU and REESS posts), not one category per statistical operation --
    useful as display context on a search result, not as a replacement
    topic taxonomy.
    """
    cached = _categories_cache.get("categories")
    if cached is not None:
        return cached

    names: dict[int, str] = {}
    async with httpx.AsyncClient(timeout=25.0) as session:
        page = 1
        while True:
            batch, _ = await _get_api_json(
                "categories", {"per_page": 100, "page": page}, session=session
            )
            if not batch:
                break
            for cat in batch:
                names[cat["id"]] = unescape(cat.get("name", ""))
            if len(batch) < 100:
                break
            page += 1

    _categories_cache.set("categories", names)
    return names


def _summarize_post(post: dict[str, Any], categories: dict[int, str]) -> dict[str, Any]:
    return {
        "id": post["id"],
        "titulo": unescape(post.get("title", {}).get("rendered", "")).strip(),
        "url": post.get("link", ""),
        "fecha_publicacion": (post.get("date") or "")[:10],
        "fecha_modificacion": (post.get("modified") or "")[:10],
        "categorias": [categories.get(cid, str(cid)) for cid in post.get("categories", [])],
    }


async def search_publicaciones(
    query: str = "", limit: int = 20, offset: int = 0
) -> dict[str, Any]:
    """
    Full-text search over every post INEC has ever published on Ecuador en
    Cifras, via its public WordPress REST API, newest first.

    This is the authoritative, always-current layer -- confirmed live to
    hold 1,707 posts, the newest within days of being checked -- unlike
    search_topics, whose topic pages can go stale for years while INEC
    keeps publishing that same operation under a post the old page never
    got updated to link. Use this for "what's the latest bulletin for X"
    questions; use search_topics/get_topic_files for one operation's fixed
    landing page instead of a specific dated release.

    Args:
        query: Free text, matched by WordPress against title/content/excerpt
            (e.g. "ENEMDU anual 2025", "inflación julio", "censo"). Empty
            returns the most recent posts regardless of topic.
        limit: Max results returned (max 100, the WordPress REST API's own
            per-page ceiling).
        offset: Pagination offset over the matched set.
    """
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    params: dict[str, Any] = {
        "per_page": limit,
        "offset": offset,
        "orderby": "date",
        "order": "desc",
        "_fields": "id,link,date,modified,title,categories",
    }
    if query:
        params["search"] = query

    async with httpx.AsyncClient(timeout=25.0) as session:
        posts, headers = await _get_api_json("posts", params, session=session)
        categories = await _fetch_categories()

    total_header = headers.get("X-WP-Total")
    results = [_summarize_post(p, categories) for p in posts]
    return {
        "total": int(total_header) if total_header is not None else None,
        "offset": offset,
        "publicaciones": results,
    }


def _extract_files_from_html(html: str) -> list[dict[str, str]]:
    seen: dict[str, str] = {}
    for url, ext in _FILE_LINK_RE.findall(html):
        seen.setdefault(url, ext.upper())
    return [{"label": _label_from_url(url), "url": url, "format": fmt} for url, fmt in seen.items()]


async def get_publicacion_files(post: int | str) -> dict[str, Any]:
    """
    Fetch one INEC publication (a WordPress post) and extract its direct
    file links, by numeric id (from search_publicaciones's "id" field) or
    by its full ecuadorencifras.gob.ec URL.

    Args:
        post: A post id from search_publicaciones, or a post URL on
            ecuadorencifras.gob.ec.
    """
    if isinstance(post, str):
        if not post.startswith(_SITE_PREFIX):
            raise ValueError(f"URL fuera de ecuadorencifras.gob.ec: {post}")
        slug = post.rstrip("/").rsplit("/", 1)[-1]
        cache_key: int | str = post
        lookup: dict[str, Any] = {"slug": slug}
    else:
        cache_key = post
        lookup = {"include": post}

    cached = _publicacion_files_cache.get(cache_key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=25.0) as session:
        matches, _ = await _get_api_json("posts", lookup, session=session)
        if not matches:
            raise ValueError(f"No se encontró la publicación '{post}' en Ecuador en Cifras")
        data = matches[0]
        categories = await _fetch_categories()

    summary = _summarize_post(data, categories)
    result = {
        **summary,
        "archivos": _extract_files_from_html(data.get("content", {}).get("rendered", "")),
    }
    _publicacion_files_cache.set(cache_key, result)
    return result

"""Client for MSP's (Ministerio de Salud Pública) weekly "Gaceta de
Inmunoprevenibles" archive — one WordPress page per reporting period
(roughly one per year, but periods roll over mid-year rather than aligning
to the calendar), each listing direct PDF links to that period's weekly
"Semana Epidemiológica" (SE) bulletins on vaccine-preventable-disease
surveillance. Found 2026-09-10 while investigating MSP's broader "Gacetas
Epidemiológicas" coverage (see docs/RESEARCH.md § Ministerio de Salud
Pública) — MSP actually runs several parallel weekly gazette series
(inmunoprevenibles, vectoriales, enfermedades de la piel/reemergentes,
indicadores); this module covers only the vaccine-preventable-disease one
Daniel asked about. The others are a known, separate follow-up.

**Page discovery is dynamic, not a hardcoded year list.** MSP's site exposes
the standard WordPress REST API (`/wp-json/wp/v2/posts`, no auth), confirmed
live: searching for "inmunoprevenibles" returns every real post matching
that term in one page (`X-WP-Total: 28`, `X-WP-TotalPages: 1` at
`per_page=100`) — filtering those results to slugs starting with
"gacetas-inmunoprevenibles" reliably finds every archive page, including
whatever period MSP creates next, without needing this module updated each
year. Two of those slugs turned out to be empty landing pages with no PDF
links at all (`gacetas-inmunoprevenibles-2`,
`enfermedades-prevenibles-por-vacunacion[-2023]`) — harmless, since a page
that yields zero PDF links simply contributes zero entries.

**Each archive page is a plain Gutenberg table** (`<table>` with plain
`<a href="...pdf">` cells) — no download-monitor/WPDM gateway, simpler than
most WordPress archives handled elsewhere in this project. Confirmed live:
8 real archive pages, 2019 through 2026 (ongoing), ~300+ PDF links total
before cross-page dedup (pages roll over mid-year, e.g. the "2021" page's
last entries are Jan 2022 SE-52; the next page then repeats SE-52/53 under
a later filename — deduped here by the PDF's own download URL, which
encodes year/month, so two genuinely different filings for the same SE
number in different years are both kept).

**Filename conventions changed at least 5 times across the archive's
history** — confirmed live, not assumed: `INMUNO_NN_YYYY.pdf` →
`INMUNO-SE-NN.pdf` → `Inmunoprevenibles-SE-NN.pdf` →
`GACETA-GENERAL-INMUNOPREVENIBLES-SE-NN.pdf` →
`Eventos-Inmunoprevenibles-CT_-DNVE-SE-NN.pdf` → `Gaceta-EPV-SE-NN.pdf`
(EPV = Enfermedades Prevenibles por Vacunación). `semana` is extracted with
a single flexible "SE" regex that tolerates all of these; `anio`/`mes` come
from the upload path (`/wp-content/uploads/YYYY/MM/...`), which stayed
consistent even as filenames didn't. Since 2024, some weeks also ship a
disease-specific companion report (confirmed: "tosferina" — whooping
cough) alongside the general one; `tipo` flags that via a filename keyword
rather than assuming only one report per week.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.salud.gob.ec"
_WP_API_URL = f"{_BASE}/wp-json/wp/v2/posts"
_ARCHIVE_SLUG_PREFIX = "gacetas-inmunoprevenibles"
_WP_TIMEOUT = 30.0

# The page list (which periods exist) changes a few times a year at most;
# each page's own PDF list changes weekly while that period is current.
# Two different TTLs, same rationale as every other archive client here.
_paginas_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_archivos_cache = TtlCache(ttl_seconds=3600.0, max_entries=1)
# Separate locks: _fetch_archivos calls _fetch_paginas while holding
# _archivos_lock, and asyncio.Lock is not reentrant -- sharing one lock
# between the two would deadlock a cache-miss call on itself.
_paginas_lock = asyncio.Lock()
_archivos_lock = asyncio.Lock()

_PDF_LINK_RE = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)
_UPLOAD_PATH_RE = re.compile(r"/wp-content/uploads/(\d{4})/(\d{2})/")
_SE_RE = re.compile(r"SE[-_]?(\d{1,3})", re.IGNORECASE)
_TOSFERINA_RE = re.compile(r"tosferina", re.IGNORECASE)


def _is_salud_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "salud.gob.ec" or host.endswith(".salud.gob.ec")


async def _fetch_paginas() -> list[str]:
    """Discover every real archive page's URL via the WordPress REST API —
    see module docstring for why this stays dynamic instead of a
    hardcoded year list."""
    cached = _paginas_cache.get("urls")
    if cached is not None:
        return cached

    async with _paginas_lock:
        cached = _paginas_cache.get("urls")
        if cached is not None:
            return cached

        logger.info("Descargando el listado de páginas de Gacetas Inmunoprevenibles del MSP")
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as session:
            resp = await session.get(
                _WP_API_URL,
                params={
                    "search": "inmunoprevenibles",
                    "per_page": 100,
                    "_fields": "slug,link",
                },
                timeout=_WP_TIMEOUT,
            )
            resp.raise_for_status()
            posts = resp.json()

        urls = [
            p["link"]
            for p in posts
            if p.get("slug", "").startswith(_ARCHIVE_SLUG_PREFIX) and _is_salud_url(p.get("link", ""))
        ]
        if urls:
            _paginas_cache.set("urls", urls)
        return urls


def _parse_archivos(html: str, pagina_url: str) -> list[dict[str, Any]]:
    archivos: list[dict[str, Any]] = []
    for m in _PDF_LINK_RE.finditer(html):
        url = m.group(1)
        if not url.startswith("http"):
            url = f"{_BASE}{url}"
        if not _is_salud_url(url):
            continue
        filename = unquote(url.rsplit("/", 1)[-1])
        upload_m = _UPLOAD_PATH_RE.search(url)
        se_m = _SE_RE.search(filename)
        archivos.append(
            {
                "titulo": filename.rsplit(".", 1)[0],
                "url": url,
                "anio": upload_m.group(1) if upload_m else None,
                "mes": upload_m.group(2) if upload_m else None,
                "semana": se_m.group(1) if se_m else None,
                "tipo": "tosferina" if _TOSFERINA_RE.search(filename) else "general",
                "pagina_origen": pagina_url,
            }
        )
    return archivos


async def _fetch_archivos() -> list[dict[str, Any]]:
    cached = _archivos_cache.get("archivos")
    if cached is not None:
        return cached

    async with _archivos_lock:
        cached = _archivos_cache.get("archivos")
        if cached is not None:
            return cached

        paginas = await _fetch_paginas()
        archivos: list[dict[str, Any]] = []
        seen: set[str] = set()
        for pagina_url in paginas:
            logger.info("Descargando página de Gacetas Inmunoprevenibles: %s", pagina_url)
            content, truncated = await download_bytes(pagina_url)
            if truncated:
                raise ValueError(f"La página de {pagina_url} superó el límite de descarga.")
            html = content.decode("utf-8", errors="replace")
            for archivo in _parse_archivos(html, pagina_url):
                if archivo["url"] in seen:
                    continue
                seen.add(archivo["url"])
                archivos.append(archivo)

        if archivos:
            _archivos_cache.set("archivos", archivos)
        return archivos


async def search_gacetas_inmunoprevenibles(query: str = "") -> dict[str, Any]:
    """
    List MSP's weekly vaccine-preventable-disease epidemiological gazettes
    ("Gaceta de Inmunoprevenibles", Semana Epidemiológica bulletins),
    2019-present.

    Args:
        query: Free text matched (accent-insensitive) against the file's
            titulo, anio, semana, or tipo ("general"/"tosferina"). Empty
            returns all files.
    """
    archivos = await _fetch_archivos()
    q = _strip(query)
    matched = [
        a
        for a in archivos
        if not q
        or q in _strip(a["titulo"])
        or q in _strip(a.get("anio"))
        or q in _strip(a.get("semana"))
        or q in _strip(a["tipo"])
    ]
    return {
        "total": len(matched),
        "total_en_archivo": len(archivos),
        "source": "MSP — Gacetas de Inmunoprevenibles (vigilancia epidemiológica semanal)",
        "url_fuente": f"{_BASE}/{_ARCHIVE_SLUG_PREFIX}/",
        "archivos": matched,
    }

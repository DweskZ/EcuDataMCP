"""Client for Empresa Eléctrica Quito's (EEQ — Quito and its concession
area in Pichincha/Napo) archive of scheduled power-cut PDFs ("Programación
cortes del servicio de energía eléctrica"), covering the 2023 and 2024
national blackout crises.

Investigated 2026-09-25 (see docs/RESEARCH.md § Trigésimo primera pasada). The PDFs
are Liferay Documents & Media files served live at
`www.eeq.com.ec/documents/d/empresa-electrica-quito/{slug}`, with slugs
named by hand and no date pattern (`vsd`, `s02-08`, `29_04_2024`,
`23-al-29-09-24`), so they cannot be guessed.

**What is closed:** the headless delivery API (`/o/headless-delivery/...`)
answers 403 to guests, and JSONWS (`/api/jsonws/dlapp/...`) answers `{}` to
every guest call even with the real site groupId (8361921) — it requires
authentication without saying so.

**What works — the site's own search page (`/search?q=horarios`):** from
mid-October 2024 EEQ published each weekly schedule as a web-content
article (structure "Horarios", tag `horarios`) whose search-result card
carries the title ("Horarios del 15 al 17 de noviembre"), the publication
date, and the PDF slug in its description. Parsing those cards enumerates
that period live, and will pick up any future article with the same tag.

**What doesn't:** the earlier PDFs (April 2024 rationing, June 2024,
September to mid-October 2024, and the October-November 2023 crisis) were
linked from pages that are not indexed as "Horarios" articles, so the site
search never returns them. They were recovered via search-engine indexing
and are kept here as `_SEED_ARCHIVOS`, each confirmed live and dated from
its own first page on 2026-09-25.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.tls import os_trust_context
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.eeq.com.ec"
_SEARCH_URL = f"{_BASE}/search"
_DOC_BASE = f"{_BASE}/documents/d/empresa-electrica-quito"
_TIMEOUT = 40.0
_SEARCH_TERM = "horarios"

# 60 is the largest page size the search portlet offers; the "horarios"
# query returned 57-61 results in total, so two pages cover it with room
# to grow.
_PAGE_SIZE = 60
_MAX_PAGES = 3

# Crisis archive, not a live feed — same long TTL as the Centrosur client.
_archivos_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

# Not reachable through the site search (see module docstring). Periods
# are copied from each PDF's first page, not inferred from the slug.
_SEED_ARCHIVOS: tuple[dict[str, str], ...] = (
    {
        "slug": "desconexion-30-31-01-1-",
        "periodo": "Lunes 30 de octubre de 2023",
        "fecha": "2023-10-30",
    },
    {
        "slug": "viernes-10-a-jueves-16",
        "periodo": "Lunes 13 a jueves 16 de noviembre de 2023",
        "fecha": "2023-11-13",
    },
    {
        "slug": "24-27-28-30",
        "periodo": "Viernes 24 a jueves 30 de noviembre de 2023",
        "fecha": "2023-11-24",
    },
    {"slug": "22-abril", "periodo": "Lunes 22 de abril de 2024", "fecha": "2024-04-22"},
    {
        "slug": "23-04-2024",
        "periodo": "Martes 23 de abril de 2024",
        "fecha": "2024-04-23",
    },
    {
        "slug": "25-04-2024",
        "periodo": "Jueves 25 de abril de 2024",
        "fecha": "2024-04-25",
    },
    {
        "slug": "26-04-2024",
        "periodo": "Viernes 26 de abril de 2024",
        "fecha": "2024-04-26",
    },
    {
        "slug": "29_04_2024",
        "periodo": "Lunes 29 de abril de 2024",
        "fecha": "2024-04-29",
    },
    {
        "slug": "30_04_2024",
        "periodo": "Martes 30 de abril de 2024",
        "fecha": "2024-04-30",
    },
    {
        "slug": "21-06-2024",
        "periodo": "Viernes 21 de junio de 2024",
        "fecha": "2024-06-21",
    },
    {
        "slug": "23-al-29-09-24",
        "periodo": "Lunes 23 a domingo 29 de septiembre de 2024",
        "fecha": "2024-09-23",
    },
    {
        "slug": "04-al-06-oct",
        "periodo": "Viernes 4 a domingo 6 de octubre de 2024",
        "fecha": "2024-10-04",
    },
    {
        "slug": "25-27",
        "periodo": "Viernes 25 a domingo 27 de octubre de 2024",
        "fecha": "2024-10-25",
    },
    {
        "slug": "mf-09-10-nov",
        "periodo": "Sábado 9 y domingo 10 de noviembre de 2024",
        "fecha": "2024-11-09",
    },
)

_CARD_RE = re.compile(r'class="card-body">(.*?)</li', re.DOTALL)
_TITLE_RE = re.compile(r'class="card-title">(.*?)</h3>', re.DOTALL)
_DESC_RE = re.compile(r'class="card-description">(.*?)</p>', re.DOTALL)
_SLUG_RE = re.compile(r"/d/empresa-electrica-quito/([^\s\"<?&]+)")
_DATE_RE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", fragment))).strip()


def _parse_search_page(page: str) -> list[dict[str, Any]]:
    """Extract schedule entries from one page of search-result cards."""
    archivos = []
    for card in _CARD_RE.findall(page):
        desc_m = _DESC_RE.search(card)
        title_m = _TITLE_RE.search(card)
        if not desc_m or not title_m:
            continue
        desc = _clean(desc_m.group(1))
        slug_m = _SLUG_RE.search(desc)

        # News articles and forms also match "horarios"; only cards whose
        # description links a document are schedules.
        if not slug_m:
            continue
        date_m = _DATE_RE.search(desc)
        archivos.append(
            {
                "slug": slug_m.group(1),
                "periodo": _clean(title_m.group(1)),
                "fecha": date_m.group(1) if date_m else None,
                "origen": "busqueda_sitio",
            }
        )
    return archivos


def _with_url(archivo: dict[str, Any]) -> dict[str, Any]:
    return {**archivo, "url": f"{_DOC_BASE}/{archivo['slug']}"}


async def _fetch_archivos() -> list[dict[str, Any]]:
    cached = _archivos_cache.get("archivos")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _archivos_cache.get("archivos")
        if cached is not None:
            return cached

        encontrados: list[dict[str, Any]] = []
        logger.info("Descargando índice de cortes de EEQ (búsqueda: %s)", _SEARCH_TERM)
        # www.eeq.com.ec omits its Sectigo intermediate; the bundled one
        # completes the chain with verification still on (helpers/tls.py).
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            verify=os_trust_context(),
        ) as session:
            for page_no in range(1, _MAX_PAGES + 1):
                resp = await session.get(
                    _SEARCH_URL,
                    params={"q": _SEARCH_TERM, "delta": _PAGE_SIZE, "start": page_no},
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                encontrados.extend(_parse_search_page(resp.text))
                if len(_CARD_RE.findall(resp.text)) < _PAGE_SIZE:
                    break

        # Seeds first so a live card for the same slug overrides them.
        by_slug = {s["slug"]: {**s, "origen": "semilla"} for s in _SEED_ARCHIVOS}
        by_slug.update({a["slug"]: a for a in encontrados})
        archivos = [_with_url(a) for a in by_slug.values()]
        archivos.sort(key=lambda a: a.get("fecha") or "", reverse=True)

        # Only cache when the live search contributed, so a broken search
        # page is retried instead of pinning the seed-only list for 6h.
        if encontrados:
            _archivos_cache.set("archivos", archivos)
        return archivos


async def search_eeq_cortes(query: str = "") -> dict[str, Any]:
    """
    List EEQ's (Quito) archive of scheduled power-cut PDFs from the 2023
    and 2024 blackout crises.

    Args:
        query: Free text matched (accent-insensitive) against periodo,
            fecha, or slug. Empty returns all files.
    """
    archivos = await _fetch_archivos()
    q = _strip(query)
    matched = [
        a
        for a in archivos
        if not q
        or q in _strip(a["periodo"])
        or q in _strip(a.get("fecha"))
        or q in _strip(a["slug"])
    ]
    return {
        "total": len(matched),
        "total_en_archivo": len(archivos),
        "source": (
            "Empresa Eléctrica Quito — Programación cortes del servicio de "
            "energía eléctrica (Quito y área de concesión)"
        ),
        "url_fuente": f"{_SEARCH_URL}?q={_SEARCH_TERM}",
        "archivos": matched,
    }

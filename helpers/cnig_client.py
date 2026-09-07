"""Client for CNIG's (Consejo Nacional para la Igualdad de Género —
igualdadgenero.gob.ec) "Violencia" page, which carries the "matriz de
femicidios" item on ROADMAP.md ("Femicidios y Homicidios Intencionales de
Mujeres") alongside 19 other gender-violence statistical tables on the same
page. Confirmed live 2026-09-02.

**Institution, disambiguated.** `igualdadgenero.gob.ec` is confirmed to be
the *gender*-equality council specifically (page title: "Consejo Nacional
para la Igualdad de Género – CNIG"), not one of Ecuador's other "Consejos
Nacionales para la Igualdad" (generacional, discapacidades, movilidad
humana, pueblos y nacionalidades). The Fiscalía General del Estado also
publishes femicide figures, but that's a separate, unrelated source (its
own "Estadísticas FGE" page — see RESEARCH.md — was abandoned since 2021);
nothing here is re-published Fiscalía data, though CNIG's PDF explicitly
says its figures are compiled *from* Consejo de la Judicatura, Fiscalía
General del Estado, and Ministerio del Interior source data.

**Reachability gotcha.** The bare domain (`curl`/plain `httpx` with no
identifying User-Agent) gets an abrupt TLS-level connection close — this
looked like a dead host at first. It isn't: a real browser reaches it fine,
and so does `helpers.csv_reader.download_bytes` (which always sends this
project's `USER_AGENT` header) — confirmed live via both a browser session
and direct `httpx` with that header. Looks like UA-based bot filtering
similar to the `seps.gob.ec` case in RESEARCH.md, not an actual outage.

**Format and cadence, verified rather than assumed.** Every item on this
page is a PDF (not CSV/XLSX) served through a WordPress download-monitor
redirect (`/wp-content/plugins/download-monitor/download.php?id=<id>`);
confirmed live for a 7-item sample. The femicide PDF's own text says
figures "se actualizan semanalmente" (updated weekly) by the source
institutions — but the *published PDF on this page* is a static snapshot:
its content is dated "corte al 09 de abril de 2023" and every file in this
section shares the exact same HTTP Last-Modified (2025-02-22), a batch
timestamp consistent with a one-time site migration rather than a rolling
weekly refresh. So: real, live, no login/CAPTCHA — but treat "weekly" as
the institution's stated intent for the underlying indicator, not a
guarantee about what's currently posted here. TTL is set generously (a
few hours) because re-scraping more often would not surface fresher data
in practice.
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

_PAGE_URL = "https://www.igualdadgenero.gob.ec/violencia/"

# See module docstring: the page itself is static (last real content
# update evidence points to well over a year stale), so a few hours is
# plenty -- it just avoids re-scraping the page on every call.
_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

# Every real entry on the page has a paired "ver"/"Descargar <TITLE>" link;
# the "Descargar" one's title attribute already carries a clean, complete
# label (matches the page's own <span class="titulo"> text), so there's no
# need to also parse the separate accordion heading.
_ENTRY_RE = re.compile(
    r'href="(https://www\.igualdadgenero\.gob\.ec/wp-content/plugins/'
    r'download-monitor/download\.php\?id=(\d+)&force=1)"\s+title="Descargar ([^"]+)"'
)
_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", html.unescape(text)).strip()


def _parse_entries(page_html: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in _ENTRY_RE.finditer(page_html):
        url, entry_id, raw_label = m.group(1), m.group(2), m.group(3)
        if entry_id in seen:
            continue
        seen.add(entry_id)
        entries.append(
            {
                "id": entry_id,
                "label": _clean(raw_label),
                "url": url,
                # Format isn't declared on the page (download-monitor URLs
                # carry no extension) -- every sampled item resolved to a
                # PDF live, so it's hardcoded rather than guessed per-item.
                "format": "PDF",
            }
        )
    return entries


async def _fetch_entries() -> list[dict[str, str]]:
    cached = _files_cache.get("entries")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _files_cache.get("entries")
        if cached is not None:
            return cached

        logger.info("Descargando la página de Violencia del CNIG (%s)", _PAGE_URL)
        content, truncated = await download_bytes(_PAGE_URL)
        if truncated:
            raise ValueError(f"La página de {_PAGE_URL} superó el límite de descarga.")
        page_html = content.decode("utf-8", errors="replace")

        entries = _parse_entries(page_html)
        if entries:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/bce_remesas_client.py / helpers/contraloria_client.py.
            _files_cache.set("entries", entries)
        return entries


async def search_femicidios(query: str = "") -> dict[str, Any]:
    """
    List (optionally filtered) CNIG "Violencia" statistical PDFs, including
    the femicide/intentional-homicide-of-women matrix.

    Args:
        query: Free text matched (accent-insensitive) against the entry's
            label, e.g. "femicidio", "lgbti", "provincia". Empty returns
            all 20 entries on the page.
    """
    entries = await _fetch_entries()
    q = _strip(query)
    matched = [e for e in entries if not q or q in _strip(e["label"])]
    return {
        "total": len(matched),
        "total_en_pagina": len(entries),
        "source": "CNIG — Consejo Nacional para la Igualdad de Género (Violencia)",
        "url_fuente": _PAGE_URL,
        "archivos": matched,
    }

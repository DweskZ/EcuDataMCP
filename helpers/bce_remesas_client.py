"""Client for BCE's dedicated Remesas de Trabajadores (worker remittances)
page (contenido.bce.fin.ec/series-de-datos-remesas-de-trabajadores/) — a
separate collection from BCEData/IEM (helpers/bce_client.py,
helpers/bce_iem_client.py), not a duplicate of either: neither exposes this
series.

Confirmed live: a small, static set of direct file links under a stable
`/documentos/.../Remesas/` path — the aggregate flow series (XLSX), the
full historical series back before the methodology change (XLSX), a user
note on methodology (PDF), and, since a July 2025 change to microdata-based
collection, two monthly database files (aggregate and entity-level, CSV).
Because the page explicitly separates historical-series and
post-July-2025-microdata files by filename/label, this client doesn't need
to (and shouldn't) merge them into one series — callers should treat
"histórica" and "BDD" results as methodologically distinct, per the
comparability note the page itself carries (Nota_al_usuario.pdf).

Only five files today, but scraped live rather than hardcoded (unlike
helpers/sipa_client.py's four fixed *module pages*) since this is a single
page that could grow a new file (e.g. a future methodology note) without
warning.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import unquote, urljoin

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_PAGE_URL = "https://contenido.bce.fin.ec/series-de-datos-remesas-de-trabajadores/"
_BASE = "https://contenido.bce.fin.ec"

# The page is hand-maintained and updates roughly monthly (new BDD files);
# a few hours balances staleness against re-fetching/re-parsing the page.
_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

# Every real file link on this page lives under this stable path segment,
# which is a more reliable anchor than the surrounding HTML/CSS classes (not
# inspected live before writing this, so not assumed stable).
_LINK_RE = re.compile(r'href="([^"]*/Remesas/[^"]+\.(?:xlsx|xls|csv|pdf|zip))"', re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def _label_from_url(url: str) -> str:
    """Derive a human label from the file's URL, same rationale as
    helpers/sri_client.py's Alfresco links: the surrounding anchor text is
    often a generic call-to-action, not a real label, while the filename
    itself (Flujo_de_remesas_de_trabajadores.xlsx,
    BDD_Remesas_de_trabajadores_entidad.csv) already is one.
    """
    filename = unquote(url.rsplit("/", 1)[-1])
    stem = filename.rsplit(".", 1)[0]
    return _WS_RE.sub(" ", stem.replace("_", " ")).strip()


def _parse_files(html: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in _LINK_RE.finditer(html):
        href = m.group(1)
        url = href if href.startswith("http") else urljoin(_BASE, href)
        if url in seen:
            continue
        seen.add(url)
        fmt = url.rsplit(".", 1)[-1].upper()
        files.append({"label": _label_from_url(url), "url": url, "format": fmt})
    return files


async def _fetch_files() -> list[dict[str, str]]:
    cached = _files_cache.get("files")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _files_cache.get("files")
        if cached is not None:
            return cached

        logger.info("Descargando la página de Remesas de Trabajadores del BCE")
        content, truncated = await download_bytes(_PAGE_URL)
        if truncated:
            raise ValueError(f"La página de {_PAGE_URL} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        files = _parse_files(html)
        if files:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/contraloria_client.py.
            _files_cache.set("files", files)
        return files


async def search_archivos(query: str = "") -> dict[str, Any]:
    """
    List (optionally filtered) BCE Remesas de Trabajadores direct file links.

    Args:
        query: Free text matched (accent-insensitive) against the file's
            label or URL. Empty returns all files.
    """
    files = await _fetch_files()
    q = _strip(query)
    matched = [
        f for f in files if not q or q in _strip(f["label"]) or q in _strip(f["url"])
    ]
    return {
        "total": len(matched),
        "total_en_pagina": len(files),
        "source": "BCE — Remesas de Trabajadores",
        "url_fuente": _PAGE_URL,
        "archivos": matched,
    }

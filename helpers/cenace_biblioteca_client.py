"""Client for CENACE's "Biblioteca" page (cenace.gob.ec/biblioteca/), the
operator's document archive documented in docs/RESEARCH.md § CENACE —
Biblioteca, tableros, despacho (Trigésimo quinta pasada).

One static ~2.2 MB page with the same WordPress download-monitor library
markup as the SGR, ARCSA and Educación Superior libraries (`ul.ul-downloads`
root, `li.li-gray1` headers with `id="cat-N"`, paired "Ver"/"Descargar
<TITLE>" `download.php?id=N&force=0/1` links). The top-level category scan
is generic, so it is imported from helpers/senescyt_biblioteca_client.py
rather than copied a fourth time; only the entry regex is host-specific.

About 2,480 entries in 11 top-level categories, mostly administrative
(viáticos, contracting). The useful ones for data work: Informe Ejecutivo de
Gestión Mensual (2016-2026), Informe Anual (2012-2025), Informe Operativo
Anual, Factor de Emisión de CO₂ (2011, 2014-2024), the semestral
Indisponibilidad del SNT reports, the POA/PEI planning documents and the
interconnection agreements with Colombia and Peru. All PDFs. `wp-json` does
not index the download monitor, so this page is the only index.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.senescyt_biblioteca_client import (
    _CAT_HEADER_RE,
    _ROOT_UL_RE,
    _top_level_categorias,
)
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BIBLIOTECA_URL = "https://www.cenace.gob.ec/biblioteca/"
_SOURCE = "CENACE — Biblioteca, cenace.gob.ec"

# New entries land monthly at most (one executive report a month, travel
# reports in batches): the same 6 h TTL as the other libraries.
_page_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_TAG_RE = re.compile(r"<[^>]+>")
_ENTRY_RE = re.compile(
    r'href="(?P<url>https?://[^"]*cenace\.gob\.ec/wp-content/plugins/'
    r'download-monitor/download\.php\?id=(?P<id>\d+)&(?:amp;)?force=1)"\s+'
    r'title="Descargar (?P<label>[^"]+)"'
)


def _clean(text: str) -> str:
    return " ".join(unescape(_TAG_RE.sub(" ", text)).split())


def _is_cenace_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("cenace.gob.ec", "www.cenace.gob.ec")


def _categoria_archivos(html: str, categoria: dict[str, Any]) -> list[dict[str, Any]]:
    """Entries in one top-level category, tagged with the nearest nested
    header (usually the year) as `subgrupo`."""
    chunk_start, chunk_end = categoria["start"], categoria["end"]
    events: list[tuple[int, str, Any]] = []
    for cm in _CAT_HEADER_RE.finditer(html, chunk_start, chunk_end):
        if cm.start() == chunk_start:
            continue
        events.append((cm.start(), "cat", _clean(cm.group("name"))))
    for em in _ENTRY_RE.finditer(html, chunk_start, chunk_end):
        events.append((em.start(), "entry", em))
    events.sort(key=lambda e: e[0])

    archivos: list[dict[str, Any]] = []
    seen: set[str] = set()
    subgrupo: str | None = None
    for _, kind, data in events:
        if kind == "cat":
            subgrupo = data
            continue
        entry_id = data.group("id")
        url = unescape(data.group("url"))
        if entry_id in seen:
            continue
        seen.add(entry_id)
        if not _is_cenace_url(url):
            logger.warning("CENACE Biblioteca: descartado link con dominio inesperado (%s).", url)
            continue

        # download.php carries no extension; the files checked are all PDFs.
        archivos.append(
            {
                "id": entry_id,
                "subgrupo": subgrupo,
                "titulo": _clean(data.group("label")),
                "url": url,
                "formato": "DESCONOCIDO",
            }
        )
    return archivos


async def _fetch_biblioteca_html() -> str:
    cached = _page_cache.get("html")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _page_cache.get("html")
        if cached is not None:
            return cached

        logger.info("Descargando la Biblioteca de CENACE (%s)", _BIBLIOTECA_URL)
        content, truncated = await download_bytes(_BIBLIOTECA_URL)
        if truncated:
            raise ValueError(f"La página de {_BIBLIOTECA_URL} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        # A page without the library root is a maintenance or error page:
        # don't pin it for the TTL.
        if _ROOT_UL_RE.search(html):
            _page_cache.set("html", html)
        return html


async def list_biblioteca_categorias() -> dict[str, Any]:
    """List the Biblioteca's top-level categories with their document counts."""
    html = await _fetch_biblioteca_html()
    categorias = [
        {
            "id": c["id"],
            "nombre": c["nombre"],
            "total_archivos": len(_ENTRY_RE.findall(html, c["start"], c["end"])),
        }
        for c in _top_level_categorias(html)
    ]
    return {
        "total": len(categorias),
        "source": _SOURCE,
        "url_fuente": _BIBLIOTECA_URL,
        "categorias": categorias,
    }


async def get_biblioteca_categoria_archivos(categoria: str) -> dict[str, Any]:
    """
    List one top-level category's documents.

    Args:
        categoria: A category id or nombre from list_biblioteca_categorias
            (nombre match is accent/case-insensitive).
    """
    html = await _fetch_biblioteca_html()
    cats = _top_level_categorias(html)
    q = _strip(categoria)
    match = next((c for c in cats if c["id"] == categoria or _strip(c["nombre"]) == q), None)
    if match is None:
        valid = ", ".join(f"{c['id']}:{c['nombre']}" for c in cats)
        raise ValueError(f"Categoría '{categoria}' no reconocida. Válidas: {valid}")

    archivos = _categoria_archivos(html, match)
    return {
        "id": match["id"],
        "nombre": match["nombre"],
        "total": len(archivos),
        "source": _SOURCE,
        "url_fuente": _BIBLIOTECA_URL,
        "archivos": archivos,
    }

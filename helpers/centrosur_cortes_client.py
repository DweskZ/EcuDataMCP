"""Client for Centrosur's (Empresa Eléctrica Regional Centro Sur — Azuay,
Cañar, Morona Santiago) archive of scheduled power-cut ("Programación de
cortes del servicio de energía eléctrica") PDFs, including the 2024
national blackout crisis (estiaje/hydrological deficit, Sep-Dec 2024).

Found 2026-09-20 while re-investigating the historical blackout archive
requested by Daniel (see docs/RESEARCH.md § Vigésimo séptima pasada) — the
first distributor in this project confirmed to expose a real, unauthenticated
enumeration mechanism for this kind of document, unlike EEQ (Liferay, no
public API, only discoverable via search-engine indexing) or CNEL (confirmed
to have no recoverable archive at all — the 2024 crisis announcements are
not present in its own WordPress, by tag or by full-text search).

**Mechanism, confirmed live:** Centrosur's institutional site runs
WordPress, and its Media Library REST API
(`www.centrosur.gob.ec/wp-json/wp/v2/media`) is public, unauthenticated, and
searchable (`?search=<term>`) — no login, no pagination guesswork needed
(each term's result set fits in one `per_page=100` page). Two search terms
are combined because Centrosur's own filenames aren't consistent:
"Cortes" (`Cortes_18_19_ABRIL_2024.pdf`,
`Cortes-23-al-29-septiembre-2024.pdf`, plus pre-crisis 2023 entries) and
"desconexion" (`DESCONEXION-30-31-01-1.pdf`,
`Desconexion-de-15-a-18-horas.pdf`). Results are filtered to
`mime_type == "application/pdf"` — both search terms also match PNG/JPEG
social-media announcement graphics (`CortesPrograAviso.jpeg`,
`programacion-cortes-celular.png`) that carry no schedule data, only a
promotional image.

**Known coverage gap, confirmed not fixable via this endpoint:** a separate
folder, `wp-content/uploads/documentospdf/CortesEstiaje/`, holds additional
2024 crisis PDFs (confirmed live to still serve files, e.g.
`Cortes_19_20_ABRIL_2024_consolidado.pdf`) that were uploaded directly to
the filesystem rather than through the WordPress media library — they never
became `wp_posts` attachments, so they never appear in this REST API's
results, searched by any term. Its directory listing is blocked (`403`).
There is no known programmatic way to enumerate that folder's contents;
recovering it would require search-engine indexing the same way EEQ's
archive does.

**`nest.centrosur.gob.ec/cortes`** is a separate Angular SPA — the *current*
outage-lookup tool, not a historical archive; a September-2024 PDF link
under that subdomain found via search engine now 301-redirects back to the
SPA's root, confirming the old static path was retired. Not used here.
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
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.centrosur.gob.ec"
_WP_MEDIA_URL = f"{_BASE}/wp-json/wp/v2/media"
_WP_TIMEOUT = 30.0

# Both terms are needed -- confirmed live, neither is a superset of the
# other's real (non-image) PDF results. See module docstring.
_SEARCH_TERMS = ("Cortes", "desconexion")

# The archive only grows a handful of entries a year outside crisis periods;
# a long TTL balances staleness against re-querying two search terms on
# every call, same rationale as every other archive client here.
_archivos_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_UPLOAD_PATH_RE = re.compile(r"/wp-content/uploads/(\d{4})/(\d{2})/")


def _parse_item(item: dict[str, Any]) -> dict[str, Any]:
    url = item.get("source_url", "")
    upload_m = _UPLOAD_PATH_RE.search(url)
    titulo = (item.get("title") or {}).get("rendered") or ""
    if not titulo:
        titulo = unquote(url.rsplit("/", 1)[-1]).rsplit(".", 1)[0]
    return {
        "titulo": titulo,
        "url": url,
        "anio": upload_m.group(1) if upload_m else None,
        "mes": upload_m.group(2) if upload_m else None,
        "fecha_subida": item.get("date"),
        "formato": url.rsplit(".", 1)[-1].upper() if "." in url else None,
    }


async def _fetch_term(term: str, session: httpx.AsyncClient) -> list[dict[str, Any]]:
    resp = await session.get(
        _WP_MEDIA_URL,
        params={
            "search": term,
            "per_page": 100,
            "_fields": "id,date,slug,title,source_url,mime_type,media_type",
        },
        timeout=_WP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


async def _fetch_archivos() -> list[dict[str, Any]]:
    cached = _archivos_cache.get("archivos")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _archivos_cache.get("archivos")
        if cached is not None:
            return cached

        archivos: list[dict[str, Any]] = []
        seen: set[int] = set()
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as session:
            for term in _SEARCH_TERMS:
                logger.info("Descargando archivo de cortes de Centrosur (búsqueda: %s)", term)
                for item in await _fetch_term(term, session):
                    if item.get("mime_type") != "application/pdf":
                        continue
                    item_id = item.get("id")
                    if item_id in seen:
                        continue
                    seen.add(item_id)
                    archivos.append(_parse_item(item))

        archivos.sort(key=lambda a: a.get("fecha_subida") or "", reverse=True)
        if archivos:
            _archivos_cache.set("archivos", archivos)
        return archivos


async def search_centrosur_cortes(query: str = "") -> dict[str, Any]:
    """
    List Centrosur's (Azuay/Cañar/Morona Santiago) archive of scheduled
    power-cut PDFs, including the 2024 hydrological-crisis blackouts.

    Args:
        query: Free text matched (accent-insensitive) against the file's
            titulo, anio, mes, or URL. Empty returns all files.
    """
    archivos = await _fetch_archivos()
    q = _strip(query)
    matched = [
        a
        for a in archivos
        if not q
        or q in _strip(a["titulo"])
        or q in _strip(a.get("anio"))
        or q in _strip(a.get("mes"))
        or q in _strip(a["url"])
    ]
    return {
        "total": len(matched),
        "total_en_archivo": len(archivos),
        "source": (
            "Centrosur — Programación de cortes del servicio de energía "
            "eléctrica (Azuay, Cañar, Morona Santiago)"
        ),
        "url_fuente": _WP_MEDIA_URL,
        "archivos": matched,
    }

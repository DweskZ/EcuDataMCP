"""Client for ARCSA's (Agencia Nacional de Regulación, Control y Vigilancia
Sanitaria) "Base de Registros Emitidos" page
(controlsanitario.gob.ec/base-de-datos/) — the live sanitary-registry
database the roadmap previously marked unreachable ("está caído (reset
TLS)"). Confirmed live again 2026-09-05: the domain responds normally with
a browser-identifying User-Agent (`helpers.user_agent.USER_AGENT`); a bare
`curl`/`httpx` request with no UA still gets a TLS reset, which is what the
earlier pass likely hit.

The page is the exact same WordPress "download-monitor" categorized-library
markup already handled by helpers/sgr_publicaciones_client.py's Biblioteca
parser (`ul.ul-downloads` root, `li.li-gray1` category headers with
`id="cat-N"`, paired "ver"/"Descargar <TITLE>" `download.php?id=N&force=0/1`
links) — confirmed live by diffing the raw HTML against that module's
regexes, not assumed from visual similarity. This module reuses that exact
parsing approach (_top_level_categorias/_categoria_archivos), scoped to
controlsanitario.gob.ec instead of gestionderiesgos.gob.ec.

Much smaller than SGR's Biblioteca: 27 top-level categories, 77 total
entries (vs. ~1660), confirmed live 2026-09-05 by parsing the real page.
9 categories nest one further level (e.g. "Inspecciones en Establecimientos
Farmacéuticos Controlados" > one sub-category per year 2016-2023;
"Medicamentos" > "Consulta de Medicamentos") — same one-level-deep nesting
SGR's Biblioteca has, surfaced the same way as each entry's "subgrupo".
Two categories are empty (0 entries): "Medicamentos incluidos en el
certificado sanitario de provisión de medicamentos" and "Bases de Datos de
Notificaciones de Publicidad ingresadas en ARCSA" — kept in list_categorias
with total_archivos=0 rather than hidden, since the category itself is a
genuine, named part of the page's structure.

Most categories hold a handful of current snapshot files (e.g. "ARCSA_LISTADO
DE MEDICAMENTOS DE VENTA LIBRE 2026", one file), not deep historical
archives — this is a registry of what's currently authorized/registered,
not a dated bulletin series. One category name is reproduced as published
even though it looks like a typo: "+NotiAlertas - Farmacovigilancia" carries
a literal leading "+" in the site's own HTML text, separate from the "+"
icon span that precedes every category — confirmed by reading the raw
markup, not a parsing artifact of this module.

Format is reported as "DESCONOCIDO" for every entry, same reasoning as SGR
Biblioteca: download.php's URL carries no file extension, and per-entry
verification isn't feasible at this scale within this pass (a small spot
check did confirm real files behind the links, e.g. a PDF listado).
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
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.controlsanitario.gob.ec"
_BASE_DATOS_URL = f"{_BASE}/base-de-datos/"

# The category list and its file counts change only when ARCSA
# adds/removes a registry category or refreshes a snapshot — matches the
# long-TTL rationale already used for SGR's Biblioteca.
_page_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return unescape(_TAG_RE.sub(" ", text)).strip()


def _is_arcsa_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "controlsanitario.gob.ec" or host.endswith(
        ".controlsanitario.gob.ec"
    )


# --- Base de Registros Emitidos (categorized download-monitor library) ---
# Same markup shape and parsing strategy as
# helpers/sgr_publicaciones_client.py's Biblioteca section — see that
# module's docstring for the full rationale of the depth-tracking approach.

_ROOT_UL_RE = re.compile(r'<ul class="ul-downloads">')
_UL_TOKEN_RE = re.compile(r"<ul\b[^>]*>|</ul>")
_CAT_HEADER_RE = re.compile(
    r'<li class="li-gray1" id="cat-(?P<id>\d+)"[^>]*>\s*'
    r'<a[^>]*><span class="ico">\+</span>(?P<name>[^<]+)</a>'
)
_ENTRY_RE = re.compile(
    r'href="(?P<url>https?://[^"]*controlsanitario\.gob\.ec/wp-content/plugins/'
    r'download-monitor/download\.php\?id=(?P<id>\d+)&(?:amp;)?force=1)"\s+'
    r'title="Descargar (?P<label>[^"]+)"'
)


def _top_level_categorias(html: str) -> list[dict[str, Any]]:
    """Find the categories that are direct children of `ul.ul-downloads`,
    as opposed to a nested sub-category sharing the exact same markup —
    identical technique to
    helpers/sgr_publicaciones_client.py's _top_level_categorias."""
    root_m = _ROOT_UL_RE.search(html)
    if root_m is None:
        return []
    start = root_m.end()

    events: list[tuple[int, str, Any]] = []
    depth = 1
    for tm in _UL_TOKEN_RE.finditer(html, start):
        if tm.group().startswith("</ul"):
            events.append((tm.start(), "close", tm.end()))
        else:
            events.append((tm.start(), "open", None))
    for cm in _CAT_HEADER_RE.finditer(html, start):
        events.append((cm.start(), "cat", cm))
    events.sort(key=lambda e: e[0])

    cats: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    for _, kind, extra in events:
        if kind == "open":
            depth += 1
        elif kind == "close":
            depth -= 1
            if depth == 0:
                if pending is not None:
                    pending["end"] = extra
                    cats.append(pending)
                    pending = None
                break
        elif kind == "cat" and depth == 1:
            if pending is not None:
                pending["end"] = extra.start()
                cats.append(pending)
            pending = {
                "id": extra.group("id"),
                "nombre": _clean(extra.group("name")),
                "start": extra.start(),
                "end": len(html),
            }
    if pending is not None:
        cats.append(pending)
    return cats


def _categoria_archivos(html: str, categoria: dict[str, Any]) -> list[dict[str, Any]]:
    """Entries within one top-level category's subtree, tagged with the
    nearest preceding *nested* category header (if any) as "subgrupo" —
    same linear scan as
    helpers/sgr_publicaciones_client.py's _categoria_archivos."""
    chunk_start, chunk_end = categoria["start"], categoria["end"]
    events: list[tuple[int, str, Any]] = []
    for cm in _CAT_HEADER_RE.finditer(html, chunk_start, chunk_end):
        if cm.start() == chunk_start:
            continue  # the category's own header, not a nested sub-category
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
        if entry_id in seen:
            continue
        seen.add(entry_id)
        url = data.group("url")
        if not _is_arcsa_url(url):
            logger.warning(
                "ARCSA base-de-datos: descartado link con dominio inesperado (%s).", url
            )
            continue
        archivos.append(
            {
                "id": entry_id,
                "subgrupo": subgrupo,
                "titulo": _clean(data.group("label")),
                "url": url,
                # See module docstring: download.php carries no extension.
                "formato": "DESCONOCIDO",
            }
        )
    return archivos


async def _fetch_base_datos_html() -> str:
    cached = _page_cache.get("html")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _page_cache.get("html")
        if cached is not None:
            return cached

        logger.info(
            "Descargando la página Base de Registros Emitidos de ARCSA (%s)",
            _BASE_DATOS_URL,
        )
        content, truncated = await download_bytes(_BASE_DATOS_URL)
        if truncated:
            raise ValueError(
                f"La página de {_BASE_DATOS_URL} superó el límite de descarga."
            )
        html = content.decode("utf-8", errors="replace")
        if _ROOT_UL_RE.search(html):
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/sgr_publicaciones_client.py.
            _page_cache.set("html", html)
        return html


async def list_categorias() -> dict[str, Any]:
    """
    List ARCSA's "Base de Registros Emitidos" top-level categories
    (Alimentos, Medicamentos, Cosméticos, Dispositivos Médicos, etc.), each
    with its own document count. A few categories nest further
    sub-categories (e.g. by year) — get_categoria_archivos surfaces those
    as each entry's "subgrupo", not as a separate category to list here.
    """
    html = await _fetch_base_datos_html()
    cats = _top_level_categorias(html)
    categorias = [
        {
            "id": c["id"],
            "nombre": c["nombre"],
            "total_archivos": len(_ENTRY_RE.findall(html[c["start"] : c["end"]])),
        }
        for c in cats
    ]
    return {
        "total": len(categorias),
        "source": "ARCSA — Base de Registros Emitidos, controlsanitario.gob.ec",
        "url_fuente": _BASE_DATOS_URL,
        "categorias": categorias,
    }


async def get_categoria_archivos(categoria: str) -> dict[str, Any]:
    """
    List one ARCSA "Base de Registros Emitidos" top-level category's
    documents.

    Args:
        categoria: A category "id" or "nombre" from list_categorias
            (nombre match is accent/case-insensitive).
    """
    html = await _fetch_base_datos_html()
    cats = _top_level_categorias(html)
    q = _strip(categoria)
    match = next(
        (c for c in cats if c["id"] == categoria or _strip(c["nombre"]) == q),
        None,
    )
    if match is None:
        valid = ", ".join(f"{c['id']}:{c['nombre']}" for c in cats)
        raise ValueError(f"Categoría '{categoria}' no reconocida. Válidas: {valid}")

    archivos = _categoria_archivos(html, match)
    return {
        "id": match["id"],
        "nombre": match["nombre"],
        "total": len(archivos),
        "source": "ARCSA — Base de Registros Emitidos, controlsanitario.gob.ec",
        "url_fuente": _BASE_DATOS_URL,
        "archivos": archivos,
    }

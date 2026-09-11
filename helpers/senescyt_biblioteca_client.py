"""Client for the Viceministerio de Educación Superior's "Biblioteca" page
(educacion.gob.ec/edusuperior/biblioteca/) — the large historical document
archive documented in docs/RESEARCH.md § SENESCYT / Educación Superior /
MINEDEC (found 2026-08-28, confirmed live again 2026-09-10 once
educacion.gob.ec — unreachable from this environment on 2026-09-10's first
pass, same symptom already seen for MIDUVI — became reachable over VPN).
Separate from helpers/senescyt_client.py (a small, 12-entry curated report
archive on a different subdomain, siau.senescyt.gob.ec) and
helpers/minedec_client.py (basic-education matrícula, same educacion.gob.ec
domain but a plain unaccordioned page, not this download-monitor library).

The page is the exact same WordPress "download-monitor" categorized-library
markup already handled by helpers/sgr_publicaciones_client.py's Biblioteca
parser and helpers/arcsa_client.py's Base de Registros Emitidos (`ul.
ul-downloads` root, `li.li-gray1` category headers with `id="cat-N"`, paired
"ver"/"Descargar <TITLE>" `download.php?id=N&force=0/1` links under
`/edusuperior/wp-content/plugins/download-monitor/`) — confirmed live by
diffing the raw HTML against those modules' regexes, not assumed from visual
similarity. This module reuses that exact parsing approach
(_top_level_categorias/_categoria_archivos), scoped to educacion.gob.ec.

Much larger than either prior instance: 17 top-level categories, 1,259 total
entries, confirmed live 2026-09-10 by parsing the real page (matches the
1,259-document figure from the 2026-08-28 research pass exactly). Top-level
categories: Insumos Construcción Diagnóstico PND-ETN 2025-2029, Consejo
Ciudadano Sectorial del SNES y SNCTI, PAC SENESCYT 2023/2024/2025 (one
category per year, not nested under a shared "PAC" parent), El Concurso de
Méritos y Oposición, Indicadores de Ciencia Tecnología e Innovación del
Ecuador (ACTI), Mecanismo de Participación Ciudadana, Dirección
Administrativa, Consejo de Participación Ciudadana, Participación
Ciudadana, Examenes Especiales, Publicaciones, Normativa, LOES, SNNA, and
Acuerdos (by far the largest, 694 of the 1,259 entries — a flat chronological
list of institutional resolutions back to at least 2015).

**Nesting is deeper here than SGR/ARCSA's confirmed one-level-deep case** —
e.g. Normativa > "Reglamento de Servicios de Registro de Títulos" > "a.
Documento inicial" > the actual file is three levels below the top category,
and the "Dirección de Registro de Títulos" material the 2026-08-28 research
pass described lives at this nested depth under Normativa/Acuerdos rather
than as its own top-level category. get_biblioteca_categoria_archivos still
only tracks the *nearest* preceding nested header as "subgrupo" (same
current-group scan as SGR/ARCSA), which for a 3-level path collapses to the
innermost label, not a full breadcrumb — the same deliberate simplification
those modules already made, just more visible at this page's depth. A
handful of ids repeat verbatim across two different top-level categories
(confirmed: 1,257 unique ids across 1,259 entries) — that is the source
filing the same document under two categories, not a parsing artifact, so
both listings are kept.

Format is reported as "DESCONOCIDO" for every entry, same reasoning as
SGR/ARCSA: download.php's URL carries no file extension, and per-entry
verification isn't feasible at this scale (a spot check in the 2026-08-28
research pass did confirm a real file behind one link — Indicadores de
Ciencia, Tecnología e Innovación del Ecuador (ACTI), a PDF).
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

_BASE = "https://educacion.gob.ec"
_BIBLIOTECA_URL = f"{_BASE}/edusuperior/biblioteca/"

# Hand-maintained document library; new entries land a handful of times a
# year at most (a new PAC year, a new Acuerdo) — same long-TTL rationale as
# helpers/sgr_publicaciones_client.py's Biblioteca.
_page_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return unescape(_TAG_RE.sub(" ", text)).strip()


def _is_edusuperior_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "educacion.gob.ec"


# --- Biblioteca (categorized download-monitor library) ---
# Same markup shape and parsing strategy as
# helpers/sgr_publicaciones_client.py's Biblioteca section and
# helpers/arcsa_client.py — see those modules' docstrings for the full
# rationale of the depth-tracking approach.

_ROOT_UL_RE = re.compile(r'<ul class="ul-downloads">')
_UL_TOKEN_RE = re.compile(r"<ul\b[^>]*>|</ul>")
_CAT_HEADER_RE = re.compile(
    r'<li class="li-gray1" id="cat-(?P<id>\d+)"[^>]*>\s*'
    r'<a[^>]*><span class="ico">\+</span>(?P<name>[^<]+)</a>'
)
_ENTRY_RE = re.compile(
    r'href="(?P<url>https?://[^"]*educacion\.gob\.ec/[^"]*/wp-content/plugins/'
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
    nearest preceding *nested* category header (if any) as "subgrupo" — see
    the module docstring for why a 3-level-deep path (confirmed live under
    Normativa/Acuerdos) still collapses to just the innermost header rather
    than a full breadcrumb."""
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
        if not _is_edusuperior_url(url):
            logger.warning(
                "SENESCYT Biblioteca: descartado link con dominio inesperado (%s).", url
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


async def _fetch_biblioteca_html() -> str:
    cached = _page_cache.get("html")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _page_cache.get("html")
        if cached is not None:
            return cached

        logger.info("Descargando la página Biblioteca de Educación Superior (%s)", _BIBLIOTECA_URL)
        content, truncated = await download_bytes(_BIBLIOTECA_URL)
        if truncated:
            raise ValueError(f"La página de {_BIBLIOTECA_URL} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")
        if _ROOT_UL_RE.search(html):
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/sgr_publicaciones_client.py.
            _page_cache.set("html", html)
        return html


async def list_biblioteca_categorias() -> dict[str, Any]:
    """
    List the Viceministerio de Educación Superior's Biblioteca top-level
    categories (PAC por año, Normativa, Acuerdos, Indicadores ACTI, etc.),
    each with its own document count. Several categories nest further
    sub-categories, some several levels deep (e.g. Normativa > Reglamento de
    Servicios de Registro de Títulos > Documento inicial) —
    get_biblioteca_categoria_archivos surfaces only the nearest nested
    header as each entry's "subgrupo", not a full breadcrumb.
    """
    html = await _fetch_biblioteca_html()
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
        "source": "Viceministerio de Educación Superior — Biblioteca, educacion.gob.ec",
        "url_fuente": _BIBLIOTECA_URL,
        "categorias": categorias,
    }


async def get_biblioteca_categoria_archivos(categoria: str) -> dict[str, Any]:
    """
    List one Biblioteca top-level category's documents.

    Args:
        categoria: A category "id" or "nombre" from
            list_biblioteca_categorias (nombre match is accent/case
            -insensitive).
    """
    html = await _fetch_biblioteca_html()
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
        "source": "Viceministerio de Educación Superior — Biblioteca, educacion.gob.ec",
        "url_fuente": _BIBLIOTECA_URL,
        "archivos": archivos,
    }

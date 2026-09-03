"""Client for gestionderiesgos.gob.ec's main WordPress site's SITREP
("Informes de Situación") archive and Biblioteca section — NOT the same
source as helpers/sgr_client.py, which talks to a *different* backend
(sgrportal.gestionderiesgos.gob.ec's ArcGIS COE2/SAT MapServer, a live
snapshot of current/in-progress emergency events and tsunami stations
only, no history). This module is the historical/document archive: a
flat, reverse-chronological index of ~54 adverse-event dossiers spanning
2016-2026 (earthquakes, forest-fire seasons, rainy seasons, landslides,
volcanic activity), each with its own page holding the actual SITREP PDF
reports, plus a 19-category document library (Biblioteca) with
resolutions, contingency plans, and threat/tsunami-evacuation maps. Where
helpers/sgr_client.py answers "what's happening right now", this module
answers "what happened, when, and where's the report" — confirmed live
2026-09-03.

**SITREP archive**
(gestionderiesgos.gob.ec/informes-de-situacion-actual-por-eventos-adversos-ecuador/)
is a flat WordPress page: `<hr>`-separated blocks, each carrying a
`<a href="...">Título</a></strong></div>` title line immediately followed
by a "Fecha ...:" line ending in "| [ESTADO]" (EN CURSO/CERRADO/EN
OBSERVACIÓN) and usually a "Descripción:" line. 54 events confirmed live,
oldest "Terremoto 7.8 Mw Manabí, Pedernales" (16 abril 2016), newest
"Incendios Forestales 2026"/"Época Lluviosa 2026" (both EN CURSO as of the
confirmation date) — a real 2016-2026 span, not just recent events. Each
event's own page then lists its actual SITREP PDFs as plain
`<a href=".../wp-content/uploads/YYYY/MM/SitRep-No-NNN-....pdf">` links,
headed by "SITREP NACIONALES:" / "SITREP PROVINCIALES – <PROVINCIA>:" /
cantonal sub-headings for the larger multi-year events (the still-open
"Época Lluviosa 2026" page alone carries 700+ PDFs across
national/provincial/cantonal reports plus matching "Infografía" PDFs) —
get_sitrep_archivos tags each entry with its nearest such heading as
"grupo" so national vs. provincial reports don't get flattened together.

**Biblioteca** (gestionderiesgos.gob.ec/biblioteca/) is a WordPress
"download-monitor" accordion, structurally identical to
helpers/cnig_client.py's pattern (a paired "ver"/"Descargar <TITLE>"
download.php?id=N link), but with real category nesting that page doesn't
have: 19 top-level categories confirmed live (an `id="cat-<N>"` `<li>`
that is a *direct* child of `<ul class="ul-downloads">` — Reformas,
Alojamientos Temporales, Normativas, Guías y Manuales, Mapas de rutas de
evacuación y puntos de encuentro ante tsunamis, Planes de Contingencia,
Taller UNGRD-JICA-BOGOTA, Asistencia Humanitaria, Publicaciones, Plan
Nacional de Seguridad Integral, Documentos, Material para Prevención,
Informes de Gestión, Resoluciones y Acuerdos, Informes Unidades
Provinciales, Mapas de Amenazas, Mapas de Probabilidad Generación
Incendios Forestales, Mapas de Tsunami, Mapas en Totems Informativos),
several of which nest a further level (province/place sub-categories,
e.g. "Mapas de Tsunami" > "Galápagos", "Mapas de Amenazas" > "EL ORO") —
confirmed by walking the real DOM, not assumed from the flatter CNIG
page. ~1660 documents total (3328 "ver"/"descarga" anchors, two per doc).

_top_level_categories walks `<ul`/`</ul>` depth from the root
`ul.ul-downloads` to tell a genuine top-level category header from a
nested one sharing the exact same markup (`li.li-gray1`, identical inline
style on the `<a>`) — naive regex matching on that markup alone conflates
the two. get_biblioteca_categoria_archivos then does a single linear scan
within one top-level category's own substring, tracking the most recently
seen nested category header as "subgrupo" (same technique
helpers/superbancos_client.py's `_parse_tablepress_archivos` uses for
`current_grupo`), rather than building a full breadcrumb stack — every
nesting case confirmed live was exactly one level deep.

**Real gotcha, confirmed live 2026-09-03, not assumed:** a meaningful
share of Biblioteca's download-monitor ids 404 ("Página no encontrada")
instead of serving a file. Spot-checked across categories: ids 7891/7890/
8081 (Reformas), 6677 (Alojamientos Temporales), 4792/4120 (Planes de
Contingencia), 14183 (Normativas) all resolve to a real file (one
confirmed live as `application/pdf`, 1.2 MB, via
`.../download.php?id=7891&force=0`), while ids 1623 (Mapas de Tsunami >
Galápagos > "Puerto Villamil"), 4050 ("PLAN DE CONTINGENCIA NACIONAL
VOLCAN COTOPAXI"), 453 ("PLAN DE CONTINGENCIA FRENTE TSUNAMIS"), and 1920
("Informe de Gestión 2012") all 404 live — and the breakage isn't cleanly
explained by id range or category (id 4120 works; the adjacent id 4050 in
the very same Planes de Contingencia category doesn't). So this module
surfaces Biblioteca as a *candidate* catalog of what the page lists, not a
guarantee every id resolves — callers should expect some dead links.
Format is reported as "DESCONOCIDO" for every Biblioteca entry for the
same reason: download.php's URL carries no file extension, and verifying
each of ~1660 entries live isn't feasible here (unlike
helpers/cnig_client.py's 20-item page, where a full-sample check was
practical and justified hardcoding "PDF").
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

_BASE = "https://www.gestionderiesgos.gob.ec"
_SITREP_INDEX_URL = f"{_BASE}/informes-de-situacion-actual-por-eventos-adversos-ecuador/"
_BIBLIOTECA_URL = f"{_BASE}/biblioteca/"

# The archive index page (list of events) only grows when a new adverse
# event starts — infrequent. Biblioteca's category list is similarly
# hand-maintained. Both get a long TTL, matching
# helpers/bce_remesas_client.py / helpers/cnig_client.py's rationale.
_sitrep_index_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_biblioteca_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
# One active event's own page (e.g. "Época Lluviosa 2026") can gain a new
# SITREP every few days while it's EN CURSO -- a much shorter TTL than the
# index, keyed per event URL since many event pages can be requested.
_sitrep_event_cache = TtlCache(ttl_seconds=3600.0, max_entries=64)

_index_lock = asyncio.Lock()
_biblioteca_lock = asyncio.Lock()
_event_locks: dict[str, asyncio.Lock] = {}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_MAX_DESCRIPCION_LEN = 500


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", text))).strip()


def _is_gestionderiesgos_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "gestionderiesgos.gob.ec" or host.endswith(".gestionderiesgos.gob.ec")


# --- SITREP archive (event index) ---

_EVENT_RE = re.compile(
    r'<a\s+href="(?P<url>https?://[^"]*gestionderiesgos\.gob\.ec/[^"#]+/)">'
    r"(?P<titulo>[^<]+)</a></strong></div>\s*"
    r'<div[^>]*>\s*<strong>Fecha[^<:]*:</strong>\s*(?P<fecha>.*?)\|'
    r"\s*(?:<strong>)?\s*<span[^>]*>\[(?P<estado>[^\]]+)\]",
    re.IGNORECASE | re.DOTALL,
)
_DESCRIPCION_RE = re.compile(
    r"Descripci[oó]n[^<:]*:</strong>\s*(?P<descripcion>.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)


def _parse_sitrep_index(html: str) -> list[dict[str, Any]]:
    eventos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _EVENT_RE.finditer(html):
        url = m.group("url")
        if not _is_gestionderiesgos_url(url) or url in seen:
            continue
        seen.add(url)
        # Best-effort: look for a "Descripción:" line in the ~1500 chars
        # following this match, i.e. within this event's own block, not
        # globally (which could otherwise grab a later/unrelated event's
        # description).
        window = html[m.end() : m.end() + 1500]
        desc_m = _DESCRIPCION_RE.search(window)
        descripcion = _clean(desc_m.group("descripcion")) if desc_m else ""
        if len(descripcion) > _MAX_DESCRIPCION_LEN:
            descripcion = descripcion[:_MAX_DESCRIPCION_LEN].rstrip() + "…"
        eventos.append(
            {
                "titulo": _clean(m.group("titulo")),
                "url": url,
                "fecha_texto": _clean(m.group("fecha")),
                "estado": _clean(m.group("estado")),
                "descripcion": descripcion,
            }
        )
    return eventos


async def _fetch_sitrep_index() -> list[dict[str, Any]]:
    cached = _sitrep_index_cache.get("eventos")
    if cached is not None:
        return cached

    async with _index_lock:
        cached = _sitrep_index_cache.get("eventos")
        if cached is not None:
            return cached

        logger.info("Descargando el índice de Informes de Situación (SITREP) de SGR")
        content, truncated = await download_bytes(_SITREP_INDEX_URL)
        if truncated:
            raise ValueError(f"La página de {_SITREP_INDEX_URL} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        eventos = _parse_sitrep_index(html)
        if eventos:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/bce_remesas_client.py / helpers/cnig_client.py.
            _sitrep_index_cache.set("eventos", eventos)
        return eventos


async def list_eventos_sitrep(query: str = "") -> dict[str, Any]:
    """
    List the SGR SITREP archive's adverse-event dossiers (2016-2026).

    Args:
        query: Free text matched (accent-insensitive) against the event's
            titulo, estado, or descripcion, e.g. "terremoto", "en curso",
            "manabi". Empty returns all events.
    """
    eventos = await _fetch_sitrep_index()
    q = _strip(query)
    matched = [
        e
        for e in eventos
        if not q
        or q in _strip(e["titulo"])
        or q in _strip(e["estado"])
        or q in _strip(e["descripcion"])
    ]
    return {
        "total": len(matched),
        "total_en_pagina": len(eventos),
        "source": "SGR — Informes de Situación (SITREP), gestionderiesgos.gob.ec",
        "url_fuente": _SITREP_INDEX_URL,
        "eventos": matched,
    }


# --- SITREP archive (one event's PDF list) ---

_PDF_LINK_RE = re.compile(
    r'<a\s+href="(?P<url>https?://[^"]*gestionderiesgos\.gob\.ec/wp-content/uploads/[^"]+\.pdf)"'
    r"[^>]*>(?P<label>[^<]+)</a>",
    re.IGNORECASE,
)
# Section headings on an event page (e.g. "SITREP NACIONALES:", "SITREP
# PROVINCIALES – AZUAY:") are plain bold/heading text ending in a colon --
# matched generically rather than enumerating every province name.
_HEADING_RE = re.compile(
    r"<(?:strong|h[1-6])[^>]*>\s*(?P<heading>[A-ZÁÉÍÓÚÑ0-9][^<:]{2,80}:)\s*</(?:strong|h[1-6])>"
)


def _parse_sitrep_event(html: str) -> list[dict[str, Any]]:
    events: list[tuple[int, str, dict[str, Any] | None]] = []
    for m in _HEADING_RE.finditer(html):
        events.append((m.start(), "heading", {"heading": _clean(m.group("heading"))}))
    for m in _PDF_LINK_RE.finditer(html):
        url = m.group("url")
        if not _is_gestionderiesgos_url(url):
            continue
        events.append((m.start(), "pdf", {"url": url, "label": _clean(m.group("label"))}))
    events.sort(key=lambda e: e[0])

    archivos: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_grupo: str | None = None
    for _, kind, data in events:
        if kind == "heading":
            current_grupo = data["heading"]
            continue
        assert data is not None
        url = data["url"]
        if url in seen:
            continue
        seen.add(url)
        archivos.append({"grupo": current_grupo, "titulo": data["label"], "url": url, "formato": "PDF"})
    return archivos


async def get_sitrep_archivos(evento_url: str) -> dict[str, Any]:
    """
    Fetch one SGR SITREP event page and list its PDF report links.

    Args:
        evento_url: An event URL from list_eventos_sitrep's "url" field.
    """
    if not _is_gestionderiesgos_url(evento_url):
        raise ValueError(
            f"URL '{evento_url}' no pertenece a gestionderiesgos.gob.ec — se esperaba una "
            "url obtenida de list_eventos_sitrep."
        )

    cached = _sitrep_event_cache.get(evento_url)
    if cached is not None:
        return cached

    lock = _event_locks.setdefault(evento_url, asyncio.Lock())
    async with lock:
        cached = _sitrep_event_cache.get(evento_url)
        if cached is not None:
            return cached

        logger.info("Descargando página de evento SITREP: %s", evento_url)
        content, truncated = await download_bytes(evento_url)
        if truncated:
            raise ValueError(f"La página de {evento_url} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        archivos = _parse_sitrep_event(html)
        result = {
            "url": evento_url,
            "total": len(archivos),
            "source": "SGR — Informes de Situación (SITREP), gestionderiesgos.gob.ec",
            "archivos": archivos,
        }
        if archivos:
            _sitrep_event_cache.set(evento_url, result)
        return result


# --- Biblioteca ---

_ROOT_UL_RE = re.compile(r'<ul class="ul-downloads">')
_UL_TOKEN_RE = re.compile(r"<ul\b[^>]*>|</ul>")
_CAT_HEADER_RE = re.compile(
    r'<li class="li-gray1" id="cat-(?P<id>\d+)"[^>]*>\s*'
    r'<a[^>]*><span class="ico">\+</span>(?P<name>[^<]+)</a>'
)
_ENTRY_RE = re.compile(
    r'href="(?P<url>https?://[^"]*gestionderiesgos\.gob\.ec/wp-content/plugins/'
    r'download-monitor/download\.php\?id=(?P<id>\d+)&(?:amp;)?force=1)"\s+'
    r'title="Descargar (?P<label>[^"]+)"'
)


def _top_level_categorias(html: str) -> list[dict[str, Any]]:
    """Find the categories that are direct children of `ul.ul-downloads`
    (as opposed to a nested sub-category sharing the exact same markup —
    see module docstring). Returns each with a `start`/`end` byte-offset
    bounding that category's own subtree in `html`, used to scope
    get_biblioteca_categoria_archivos to one category at a time."""
    root_m = _ROOT_UL_RE.search(html)
    if root_m is None:
        return []
    start = root_m.end()

    # depth=1 as soon as we're inside the root <ul>; a top-level category
    # header is one seen while depth==1 (i.e. not inside any category's
    # own child <ul> yet).
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

    # A category's subtree can contain several sibling <ul> children of
    # its own (one per file entry -- confirmed live: Reformas alone has
    # one <ul> per document, not one shared <ul>), so a category only
    # really ends when either the *next* top-level category header
    # appears, or the root <ul> itself closes -- not merely when depth
    # returns to 1 after any single child <ul> closes (that would cut the
    # category off after its first file).
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
    nearest preceding *nested* category header (if any) as "subgrupo" --
    a linear "current group" scan, same technique as
    helpers/superbancos_client.py's _parse_tablepress_archivos."""
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
        archivos.append(
            {
                "id": entry_id,
                "subgrupo": subgrupo,
                "titulo": _clean(data.group("label")),
                "url": data.group("url"),
                # See module docstring: download.php carries no extension
                # and per-entry verification isn't feasible at this scale.
                "formato": "DESCONOCIDO",
            }
        )
    return archivos


async def _fetch_biblioteca_html() -> str:
    cached = _biblioteca_cache.get("html")
    if cached is not None:
        return cached

    async with _biblioteca_lock:
        cached = _biblioteca_cache.get("html")
        if cached is not None:
            return cached

        logger.info("Descargando la página Biblioteca de SGR (%s)", _BIBLIOTECA_URL)
        content, truncated = await download_bytes(_BIBLIOTECA_URL)
        if truncated:
            raise ValueError(f"La página de {_BIBLIOTECA_URL} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")
        if _ROOT_UL_RE.search(html):
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/bce_remesas_client.py / helpers/cnig_client.py.
            _biblioteca_cache.set("html", html)
        return html


async def list_biblioteca_categorias() -> dict[str, Any]:
    """
    List Biblioteca's top-level categories (Reformas, Normativas, Mapas de
    Tsunami, Planes de Contingencia, etc.), each with its own document
    count. Several categories nest further sub-categories (e.g. by
    province) — get_biblioteca_categoria_archivos surfaces those as each
    entry's "subgrupo", not as a separate category to list here.
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
        "source": "SGR — Biblioteca, gestionderiesgos.gob.ec",
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
        "source": "SGR — Biblioteca, gestionderiesgos.gob.ec",
        "url_fuente": _BIBLIOTECA_URL,
        "archivos": archivos,
    }

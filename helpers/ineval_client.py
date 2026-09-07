"""Client for INEVAL (Instituto Nacional de Evaluación Educativa)'s public
data portal (evaluaciones.evaluacion.gob.ec/BI/) -- a completely different
institution from SENESCYT/MINEDUC, and from the "Resoluciones del Ineval"
regulatory section on the separate evaluacion.gob.ec institutional site
(skipped here: administrative resolutions, not exam data).

Live-verified 2026-09-02 (re-verifying earlier research notes, which turned
out partly stale -- see below):

- The portal is WordPress-based. Its "Categoría Bases de Datos" hub
  (/BI/category/base_de_datos/) is the authoritative list of evaluation
  families with real downloadable data -- confirmed by fetching it live and
  cross-checking every listed slug. It currently lists 9 families (hardcoded
  in _FAMILIAS below): Ser Bachiller, Ser Estudiante, Ser Estudiante en la
  Infancia, Ser Estudiante en la Mitad del Mundo, Ser Estudiante Galápagos,
  Ser Maestro, Ser Maestro Recategorización, Ser Profesional, and Llece
  (ERCE/SERCE/TERCE rounds). A 10th category entry, "Informes de resultados
  nacionales", was checked and dropped: its page carries no
  /BI/download/ links at all -- pure navigation, not a data family.

- CORRECTION to prior research: the earlier pass described a per-family
  page as one "Bootstrap-accordion" with one panel per school year and
  found the family slug "historico-ser-bachiller". That slug is real but is
  an INFORMATIONAL page (methodology Q&A text, no downloads) -- a decoy
  that happens to share the top nav with the real data page. The actual
  downloadable-files page for Ser Bachiller lives at a *different* slug,
  "ser-bachiller-2" (discovered only via the Bases de Datos category hub,
  not the top nav, which links to the informational page instead). Every
  family's real slug was independently confirmed the same way -- do not
  guess a slug from the nav menu.

- Each real family page nests, under an "Datos por periodo" heading, a
  Bootstrap accordion with one panel per "Año lectivo YYYY-YYYY" (or, for
  Llece/Ser Maestro/Ser Profesional/Ser Maestro Recategorización, "Año
  YYYY" -- these run on a calendar-year cycle, not a school-year one).
  Llece additionally nests three separate accordions under bare "Erce"/
  "Serce"/"Terce" <h2> group headings -- ERCE/SERCE/TERCE are LLECE's three
  historical rounds, each with its own year(s). Confirmed live: this really
  is static HTML already in the DOM (CSS-collapsed, not JS/AJAX-rendered)
  -- a bare httpx GET returns the full accordion content, panels included.

- Each accordion panel holds an HTML <table>: row 1 is a header naming the
  formats published that period (observed: Sintaxis, CSV, SAV, XLSX/XLS,
  Metadato, Diccionario -- the exact set and column order varies panel to
  panel, so it is read fresh from each table's own header row rather than
  assumed fixed); each following row is one dataset (e.g. "Micro",
  "Factores Asociados estudiantes", "Directivos") with one download-icon
  link per format it was published in (empty cells are common -- not every
  dataset ships every format every year). Ser Estudiante and Ser Bachiller
  additionally carry a handful of standalone "Descargar ..." buttons
  outside any year table (fichas metodológicas vigentes, historical
  manuals, "información estadística") -- collected separately below since
  they have no year/format context, just a label.

- Confirmed a real download end-to-end: GET on a
  /BI/download/{id}/ (or .../{id}, trailing slash optional) URL returns
  the file directly -- no login, no CAPTCHA, no redirect page -- with a
  Content-Disposition header giving the true filename (e.g.
  "SEST25_Micro_20251215_SINTAXIS.zip" for a 27.5 KB CSV-format zip
  fetched from a Ser Estudiante 2024-2025 row). Some IDs instead answer
  with a 308 redirect straight to a static /archivosPD/uploads/... URL
  (one PDF manual observed there, 3.8 MB) -- both forms work fine through
  a redirect-following client and are treated identically here (only the
  page's own href is exposed; the caller downloads it).

- Real gotcha (do not skip): at least one family page (Ser Maestro,
  "ser-maestro-2") wraps a stale, superseded <tr> of download links inside
  an HTML comment (`<!-- ZZZZ ... -->`) directly beside the real,
  current row -- both rows are shaped identically and a regex blind to
  HTML comments would silently include dead/duplicate IDs. All HTML is
  comment-stripped before parsing here.

Files are never downloaded here -- only metadata and the direct URL, same
pattern as helpers/sipa_client.py and helpers/superbancos_client.py. Point
the model at the URL directly rather than routing it through
download_resource/preview_resource_data.
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

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://evaluaciones.evaluacion.gob.ec/BI"

_FAMILIAS: list[dict[str, str]] = [
    {
        "familia": "ser_bachiller",
        "nombre": "Ser Bachiller",
        "url": f"{_BASE}/ser-bachiller-2/",
    },
    {
        "familia": "ser_estudiante",
        "nombre": "Ser Estudiante",
        "url": f"{_BASE}/ser-estudiante-2/",
    },
    {
        "familia": "ser_estudiante_infancia",
        "nombre": "Ser Estudiante en la Infancia",
        "url": f"{_BASE}/ser-estudiante-en-la-infancia-4/",
    },
    {
        "familia": "ser_estudiante_mitad_del_mundo",
        "nombre": "Ser Estudiante en la Mitad del Mundo",
        "url": f"{_BASE}/ser-estudiante-en-la-mitad-del-mundo/",
    },
    {
        "familia": "ser_estudiante_galapagos",
        "nombre": "Ser Estudiante Galápagos",
        "url": f"{_BASE}/ser-estudiante-galapagos/",
    },
    {
        "familia": "ser_maestro",
        "nombre": "Ser Maestro",
        "url": f"{_BASE}/ser-maestro-2/",
    },
    {
        "familia": "ser_maestro_recategorizacion",
        "nombre": "Ser Maestro Recategorización",
        "url": f"{_BASE}/ser-maestro-recategorizacion/",
    },
    {
        "familia": "ser_profesional",
        "nombre": "Ser Profesional",
        "url": f"{_BASE}/ser-profesional/",
    },
    {
        "familia": "llece",
        "nombre": "Llece (ERCE / SERCE / TERCE)",
        "url": f"{_BASE}/llece-2/",
    },
]
_FAMILIAS_BY_KEY = {f["familia"]: f for f in _FAMILIAS}

# Family pages change a few times a year at most (a new school year's
# results published). max_entries matches the fixed key space.
_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=len(_FAMILIAS))
_fetch_lock = asyncio.Lock()

_TAG_RE = re.compile(r"<[^>]+>")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

_TABLE_RE = re.compile(r'<table class="table">(?P<body>.*?)</table>', re.DOTALL)
_ROW_RE = re.compile(r"<tr[^>]*>(?P<row>.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<td[^>]*>(?P<cell>.*?)</td>", re.DOTALL)
_CELL_LINK_RE = re.compile(r'<a[^>]*href="(?P<url>[^"]+)"', re.DOTALL)

# Each accordion panel's period label, e.g. "Año lectivo 2024-2025" or
# "Año 2019" (Llece/Ser Maestro/Ser Profesional/Ser Maestro
# Recategorización run calendar-year cycles, not school-year ones).
_STRONG_RE = re.compile(r"<strong>\s*(?P<periodo>.*?)\s*</strong>", re.DOTALL)
# Bare <h2>NAME</h2> (no attributes) -- only Llece's ERCE/SERCE/TERCE round
# headings use this; every other <h2> on these pages carries a
# gb-headline... class and is page chrome, not a data grouping.
_GRUPO_H2_RE = re.compile(r"<h2>\s*(?P<grupo>[^<]+?)\s*</h2>")
# Section headings above the accordion/standalone buttons, e.g. "Bases de
# datos", "Fichas metodológicas vigentes", "Manuales de fichas
# metodológicas históricas", "Información Estadística".
_SECCION_H3_RE = re.compile(r"<h3>\s*(?P<seccion>[^<]+?)\s*</h3>")
# Standalone "Descargar ..." buttons outside any year table (class="mint3"
# is unique to these -- table cells use a bare icon-only <a>, never this
# class, so the two anchor kinds never collide).
_MINT_BTN_RE = re.compile(
    r'<a class="mint3"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<label>.*?)</a>',
    re.DOTALL,
)


def _clean(text: str) -> str:
    text = unescape(_TAG_RE.sub("", text)).strip()
    return re.sub(r"\s+", " ", text)


def _is_ineval_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "evaluaciones.evaluacion.gob.ec"


def _nearest_before(matches: list[re.Match], pos: int) -> re.Match | None:
    """Last match (matches must be in document order) starting before pos,
    or None if none does. Used to attribute a table/button to the nearest
    preceding periodo/grupo/seccion heading."""
    best = None
    for m in matches:
        if m.start() >= pos:
            break
        best = m
    return best


def list_familias() -> list[dict[str, str]]:
    """The nine fixed INEVAL evaluation families with a real 'Bases de
    Datos' download page, per the site's own Categoría Bases de Datos hub."""
    return [dict(f) for f in _FAMILIAS]


def _parse_familia_archivos(html: str, familia: str) -> list[dict[str, Any]]:
    # Strip HTML comments first -- see module docstring: at least one real
    # family page hides a stale, superseded <tr> of download links inside
    # a comment, shaped identically to the live row beside it.
    html = _COMMENT_RE.sub("", html)

    grupo_matches = list(_GRUPO_H2_RE.finditer(html))
    seccion_matches = list(_SECCION_H3_RE.finditer(html))

    archivos: list[dict[str, Any]] = []

    # Pass 1: per-period "Bases de datos" tables.
    for table_m in _TABLE_RE.finditer(html):
        start = table_m.start()

        strong_m = _nearest_before(list(_STRONG_RE.finditer(html, 0, start)), start)
        periodo = _clean(strong_m.group("periodo")) if strong_m else None

        grupo_m = _nearest_before(grupo_matches, start)
        grupo = _clean(grupo_m.group("grupo")) if grupo_m else None

        rows = list(_ROW_RE.finditer(table_m.group("body")))
        if not rows:
            continue
        header_cells = [_clean(c.group("cell")) for c in _CELL_RE.finditer(rows[0].group("row"))]
        if not header_cells:
            logger.warning(
                "Ineval familia %s: tabla sin fila de encabezado reconocible -- se omite.",
                familia,
            )
            continue

        for row_m in rows[1:]:
            cells = list(_CELL_RE.finditer(row_m.group("row")))
            if not cells:
                continue
            archivo_nombre = _clean(cells[0].group("cell"))
            if not archivo_nombre:
                continue
            for idx, cell_m in enumerate(cells[1:], start=1):
                link_m = _CELL_LINK_RE.search(cell_m.group("cell"))
                if link_m is None:
                    # Empty cell -- that format wasn't published for this
                    # dataset in this period, not a parsing failure.
                    continue
                url = link_m.group("url")
                if not _is_ineval_url(url):
                    logger.warning(
                        "Ineval familia %s: descartado link con dominio inesperado (%s).",
                        familia,
                        url,
                    )
                    continue
                formato = header_cells[idx] if idx < len(header_cells) and header_cells[idx] else "DESCONOCIDO"
                archivos.append(
                    {
                        "grupo": grupo,
                        "periodo": periodo,
                        "titulo": archivo_nombre,
                        "formato": formato.upper(),
                        "url": url,
                    }
                )

    # Pass 2: standalone "Descargar ..." buttons (fichas metodológicas
    # vigentes/históricas, información estadística) -- no year/table
    # context, so periodo is intentionally left None rather than guessed
    # from whatever accordion panel happens to precede them in the HTML
    # (some sit after the whole accordion, where the "nearest preceding
    # strong" would be the LAST year's panel -- wrong).
    for btn_m in _MINT_BTN_RE.finditer(html):
        url = btn_m.group("url")
        if not _is_ineval_url(url):
            logger.warning(
                "Ineval familia %s: descartado link con dominio inesperado (%s).",
                familia,
                url,
            )
            continue
        seccion_m = _nearest_before(seccion_matches, btn_m.start())
        grupo = _clean(seccion_m.group("seccion")) if seccion_m else None
        archivos.append(
            {
                "grupo": grupo,
                "periodo": None,
                "titulo": _clean(btn_m.group("label")),
                "formato": "DESCONOCIDO",
                "url": url,
            }
        )

    return archivos


async def get_familia_archivos(familia: str) -> dict[str, Any]:
    """
    Fetch one INEVAL evaluation family's "Bases de Datos" page and list its
    direct download links.

    Args:
        familia: One of the keys from list_familias() (e.g. "ser_bachiller",
            "ser_estudiante", "llece").
    """
    info = _FAMILIAS_BY_KEY.get(familia)
    if info is None:
        valid = ", ".join(sorted(_FAMILIAS_BY_KEY))
        raise ValueError(f"Familia '{familia}' no reconocida. Válidas: {valid}")

    cached = _files_cache.get(familia)
    if cached is not None:
        return cached

    async with _fetch_lock:
        # Re-check: another caller may have populated the cache while we
        # were waiting for the lock.
        cached = _files_cache.get(familia)
        if cached is not None:
            return cached

        logger.info("Descargando página de familia Ineval: %s", familia)
        content, truncated = await download_bytes(info["url"])
        if truncated:
            raise ValueError(f"La página de {info['url']} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        archivos = _parse_familia_archivos(html, familia)
        result = {
            "familia": familia,
            "nombre": info["nombre"],
            "url": info["url"],
            "archivos": archivos,
        }
        if archivos:
            # Don't cache an apparently-empty result for 6h -- it's
            # indistinguishable from a transient failure (maintenance page,
            # stripped accordion) that would otherwise self-correct on the
            # next call.
            _files_cache.set(familia, result)
        return result

"""Client for SENESCYT's SIAU (Sistema Integrado de Analítica Universitaria)
statistics page
(siau.senescyt.gob.ec/estadisticas-de-educacion-superior-ciencia-tecnologia-e-innovacion/)
— a real report archive found 2026-08-29 (see docs/RESEARCH.md § SENESCYT /
Educación Superior / MINEDEC), separate from this project's existing SENESCYT
coverage (CKAN `organization=secretaria-de-educacion-superior-...`, the
captcha-gated título registry, and MINEDEC's basic-education matrícula in
helpers/minedec_client.py).

Confirmed live 2026-09-10. The page is a WPBakery accordion ("w-tabs") with
10 tabs, mixing two real download mechanisms on the same page:

- **WordPress Download Manager (WPDM)** package shortcodes (8 entries): each
  renders its own `<h3><a>TÍTULO</a></h3>` followed by a `Size`/`Last
  Updated` badge list and a `data-downloadurl="…/download/<slug>/?wpdmdl=ID&
  refresh=…"` gateway link. That gateway URL is a real, fetchable redirect
  to the file (confirmed live for "Indicadores de Ciencia, Tecnología e
  Innovación del Ecuador (ACTI)" as a PDF by a prior research pass against
  the sibling educacion.gob.ec/edusuperior/biblioteca/ page, same WPDM
  plugin) — but the redirect target's extension isn't visible in the page
  HTML itself, so `formato` is "DESCONOCIDO" for every WPDM entry, same
  reasoning as helpers/sgr_publicaciones_client.py's Biblioteca section.
- **Plain "Descargar" buttons** (4 entries across 3 tabs) pointing directly
  at either a same-origin `/wp-content/uploads/.../*.zip` file (format
  inferred from the extension) or a Nextcloud share link on
  `cloud-00.senescyt.gob.ec`/`cloud-pro.senescyt.gob.ec` (format unknown —
  a share link serves whatever file was uploaded, not visible from the URL
  alone, so also "DESCONOCIDO").

One tab ("Reporte de indicadores año 2021") holds two *different* WPDM
packages ("Productos intermedios", "Reporte de indicadores") under one
accordion title, and one tab ("Reporte de indicadores año 2024") holds two
plain links ("Primera parte", "Segunda parte") — both are real, not parsing
duplicates, confirmed by reading the raw markup. Each entry's own title is
kept as `titulo` (the WPDM package's own `<h3>`, or the button's visible
label for a plain link); `seccion` carries the surrounding tab's title so a
caller can tell which accordion section grouped multiple entries together.

Total: 12 entries across 10 tabs, confirmed live 2026-09-10 (up from the
first-found titles listed in RESEARCH.md's 2026-08-29 pass — this is a small,
curated report archive, not a bulk registry, so a full re-parse each call is
cheap and the flat total is checked directly rather than assumed stable).

**Known gap, not built here:** the much larger sibling archive
(educacion.gob.ec/edusuperior/biblioteca/, ~1,259 documents, confirmed live
in an earlier research pass as the same WPDM/download-monitor markup as
helpers/sgr_publicaciones_client.py's Biblioteca) could not be re-verified
today — educacion.gob.ec (the same domain already serving
helpers/minedec_client.py) is currently unreachable from this environment
(`SSL: UNEXPECTED_EOF_WHILE_READING` / connect timeout on repeated retries,
2026-09-10), the same symptom already documented for MIDUVI in
docs/RESEARCH.md. That domain being down also means
`search_minedec_matricula` is unable to serve live data right now. Building
the Biblioteca client is deferred until the domain responds again; see
docs/ROADMAP.md.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import unquote, urlparse

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_PAGE_URL = (
    "https://siau.senescyt.gob.ec/"
    "estadisticas-de-educacion-superior-ciencia-tecnologia-e-innovacion/"
)

# Hand-maintained report page, refreshed a few times a year at most (new
# annual report) — same long-TTL rationale as
# helpers/sgr_publicaciones_client.py's Biblioteca.
_page_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_FORMATO_EXTENSIONS = {"zip", "pdf", "xlsx", "xls", "docx", "doc", "csv"}

_SECTION_RE = re.compile(
    r'<div class="w-tabs-section"[^>]*>.*?'
    r'<div class="w-tabs-section-title">(?P<titulo>[^<]+)</div>',
    re.DOTALL,
)
_WPDM_ENTRY_RE = re.compile(
    r'<h3[^>]*><a href="[^"]*"><strong>(?P<titulo>[^<]+)</strong></a></h3>\s*'
    r'<ul class="list-group[^"]*">(?P<meta>.*?)</ul>\s*'
    r"<a class='wpdm-download-link[^']*'[^>]*"
    r'data-downloadurl="(?P<url>[^"]+)"',
    re.DOTALL,
)
_WPDM_SIZE_RE = re.compile(r'Size <span[^>]*>(?P<size>[^<]*)</span>')
_WPDM_UPDATED_RE = re.compile(r'Last Updated <span[^>]*>(?P<updated>[^<]*)</span>')
_DIRECT_LINK_RE = re.compile(
    r'<a class="w-btn[^"]*"[^>]*href="(?P<url>[^"]+)"><span class="w-btn-label">'
    r"(?P<label>[^<]+)</span>"
)


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", text))).strip()


def _is_senescyt_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host.endswith("senescyt.gob.ec")


def _infer_formato(url: str) -> str:
    """Extension-based format, same convention as every other client in this
    project — a WPDM gateway URL or a Nextcloud share link carries no
    extension at all, so those correctly fall through to "DESCONOCIDO"."""
    path = unquote(urlparse(url).path)
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return ext.upper() if ext in _FORMATO_EXTENSIONS else "DESCONOCIDO"


def _parse_archivos(html: str) -> list[dict[str, Any]]:
    sections = [(m.start(), _clean(m.group("titulo"))) for m in _SECTION_RE.finditer(html)]
    archivos: list[dict[str, Any]] = []
    seen: set[str] = set()

    for i, (start, seccion) in enumerate(sections):
        end = sections[i + 1][0] if i + 1 < len(sections) else len(html)
        chunk = html[start:end]

        for m in _WPDM_ENTRY_RE.finditer(chunk):
            url = m.group("url")
            if url in seen or not _is_senescyt_url(url):
                continue
            seen.add(url)
            meta = m.group("meta")
            size_m = _WPDM_SIZE_RE.search(meta)
            updated_m = _WPDM_UPDATED_RE.search(meta)
            archivos.append(
                {
                    "seccion": seccion,
                    "titulo": _clean(m.group("titulo")),
                    "url": url,
                    "tamano": _clean(size_m.group("size")) if size_m else None,
                    "actualizado": _clean(updated_m.group("updated")) if updated_m else None,
                    "tipo": "wpdm",
                    "formato": _infer_formato(url),
                }
            )

        for m in _DIRECT_LINK_RE.finditer(chunk):
            url = m.group("url")
            if url in seen:
                continue
            # Direct links point either same-origin or at a Nextcloud share
            # on a senescyt.gob.ec subdomain — both are expected; anything
            # else would be a WPBakery "Ir al portal"-style button instead
            # of a real download, which the chunk boundary should already
            # exclude (tab content only), kept as a defensive skip.
            if not _is_senescyt_url(url):
                continue
            seen.add(url)
            label = _clean(m.group("label"))
            archivos.append(
                {
                    "seccion": seccion,
                    "titulo": f"{seccion} — {label}" if label != "Descargar" else seccion,
                    "url": url,
                    "tamano": None,
                    "actualizado": None,
                    "tipo": "directo",
                    "formato": _infer_formato(url),
                }
            )

    return archivos


async def _fetch_archivos() -> list[dict[str, Any]]:
    cached = _page_cache.get("archivos")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _page_cache.get("archivos")
        if cached is not None:
            return cached

        logger.info("Descargando la página de Estadísticas de Educación Superior de SENESCYT")
        content, truncated = await download_bytes(_PAGE_URL)
        if truncated:
            raise ValueError(f"La página de {_PAGE_URL} superó el límite de descarga.")
        html = content.decode("utf-8", errors="replace")

        archivos = _parse_archivos(html)
        if archivos:
            # Same "don't cache an apparently-broken/empty scrape" rationale
            # as helpers/sgr_publicaciones_client.py.
            _page_cache.set("archivos", archivos)
        return archivos


async def search_estadisticas(query: str = "") -> dict[str, Any]:
    """
    List (optionally filtered) SENESCYT SIAU higher-education/CTI statistics
    reports: methodology sheets, annual indicator reports, the national
    competitiveness index, the CTI/ancestral-knowledge indicator inventory,
    labor-demand characterization, and the COVID-19 impact study.

    Args:
        query: Free text matched (accent-insensitive) against the file's
            seccion, titulo, tipo ("wpdm"/"directo"), or URL. Empty returns
            all files.
    """
    archivos = await _fetch_archivos()
    q = _strip(query)
    matched = [
        f
        for f in archivos
        if not q
        or q in _strip(f["seccion"])
        or q in _strip(f["titulo"])
        or q in _strip(f["tipo"])
        or q in _strip(f["url"])
    ]
    return {
        "total": len(matched),
        "total_en_pagina": len(archivos),
        "source": "SENESCYT — SIAU, Estadísticas de Educación Superior, CTI",
        "url_fuente": _PAGE_URL,
        "archivos": matched,
    }

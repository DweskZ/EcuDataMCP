"""Client for three IESS (Instituto Ecuatoriano de Seguridad Social,
iess.gob.ec) document archives, all served by the same Liferay
document-library engine (`document_library_display`) under
`iess.gob.ec/documents/10162/<folder_id>/<filename>`:

- **Boletines Estadísticos** (`iess.gob.ec/es/estadisticas`) — annual
  statistical bulletins. **26 confirmed live** (portlet `zIm8`, root folder
  `8421754`), spanning 1978-2024, not just 2006-2024 as an earlier
  investigation note assumed after only checking the list page's first 20
  rows — the archive is paginated (`cur2`/`delta2` query params) and a
  second page holds 6 more, back to "BOLETIN ESTADISTICO 01" (1978).
- **Estudios Actuariales** (`iess.gob.ec/estudios-actuariales/`) — actuarial
  valuation studies. The index page currently links **4** year sets (2010,
  2013, 2018, 2020) — discovered by parsing the page's own
  "Estudios/Actuariales YYYY" links, never hardcoded, so a year IESS adds or
  removes later is picked up automatically. Confusingly, the "2013" label
  points at the *base* `estudios-actuariales` URL (no year suffix) rather
  than an `-2013` URL — that URL pattern simply doesn't exist for 2013 (a
  live check of `-2007` through `-2025` found only `-2010`/`-2018`/`-2020`
  responding 200, everything else 404). Two different page layouts are
  handled: 2018/2020 (and the 2013 base page) link straight to
  `documents/10162/<folder>/<file>`; 2010 instead uses an entirely
  different static path, `iess.gob.ec/informacion/Estudios_Actuariales_2010/
  <file>.pdf` — not the Liferay pattern at all.
- **Informes de Auditoría** (`iess.gob.ec/es/informes-de-auditoria`) —
  internal/governmental audit reports. Three levels: an index page listing
  one Liferay folder per year (portlet `vu7F`, **2007-2026 confirmed live,
  20 folders** — one more than the 2007-2025 an earlier note described,
  since 2026 has since opened, currently empty), each folder page listing
  that year's documents (1-42 per year, paginated the same way as
  Boletines), and each document's own detail page carrying the real
  download link. **325 documents confirmed live 2026-09-04** (an earlier
  estimate said "~344" from a partial check) across the 20 year-folders.

**The real download link never comes from a listing page directly** — every
listing page (Boletines' main list, an Actuariales year's own page is the
one exception, see below, and each Auditoría year-folder) only links to a
Liferay *view* page for that document. The view page then holds the actual
`documents/10162/...` URL inside a `<a class="taglib-icon" ...><img
class="icon" src=".../file_system/large/<ext>.png" ...>` "Descargar" block
— `<ext>` (confirmed live: always `pdf` so far) is the *reliable* format
signal, not the URL's file extension. **This is the fix for a real bug an
earlier investigation pass hit and corrected**: Informes de Auditoría's real
PDF links frequently carry no `.pdf` suffix at all (e.g.
`.../documents/10162/25751514/DNA7-SySS-0001-2024?version=1.0`, confirmed
`Content-Type: application/pdf` live) — a naive scraper that only accepts
`.pdf`-suffixed URLs silently drops most of the archive. Reading the
`large/<ext>.png` icon instead of the URL avoids that trap without needing
a live `Content-Type` HEAD request per document (`helpers.csv_reader.
sniff_content_type` would work too, but at up to 42 requests per year
that's needless network cost when the server already states the format in
the same page that carries the link).

Estudios Actuariales is the one collection where a document's real link is
already on the year page itself — no Liferay view-page hop needed — but the
same no-extension gotcha still shows up there (2018's "Seguro de Desempleo"
and "Seguro Riesgos del Trabajo" links carry no `.pdf` suffix; confirmed
live via `Content-Type: application/pdf` header + `Content-Disposition`
naming them `.pdf`). Since every Actuariales document confirmed so far is a
PDF and sniffing all of them isn't worth the added requests at this scale,
extensionless entries are reported as "PDF" (assumed), documented as such
per document rather than silently guessed.

Every list/get function below returns metadata + a direct URL only, never
document content — same pattern as every other document-archive source in
this repo (SGR, Contraloría, INEVAL, Superbancos): pass the URL to
`read_pdf` to actually read one.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any

import httpx

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.iess.gob.ec"

_BOL_LIST_URL = f"{_BASE}/es/estadisticas"
_BOL_PORTLET = "zIm8"
_BOL_ROOT = "8421754"

_ACT_INDEX_URL = f"{_BASE}/estudios-actuariales/"

_AUD_LIST_URL = f"{_BASE}/es/informes-de-auditoria"
_AUD_PORTLET = "vu7F"

# These three archives are historical/append-only (a new bulletin, actuarial
# study, or audit-report year appears at most a few times a year), so a long
# TTL is appropriate -- same rationale as helpers/sgr_publicaciones_client.py's
# index caches.
_TTL = 21600.0

_boletines_cache = TtlCache(ttl_seconds=_TTL, max_entries=1)
_actuariales_cache = TtlCache(ttl_seconds=_TTL, max_entries=1)
_auditoria_anios_cache = TtlCache(ttl_seconds=_TTL, max_entries=1)
_auditoria_docs_cache = TtlCache(ttl_seconds=_TTL, max_entries=32)

_boletines_lock = asyncio.Lock()
_actuariales_lock = asyncio.Lock()
_auditoria_anios_lock = asyncio.Lock()
_auditoria_docs_locks: dict[str, asyncio.Lock] = {}

# Bound concurrent detail-page fetches per call -- polite to the origin
# server even when a single year holds up to 42 documents.
_DETAIL_CONCURRENCY = 6

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_YEAR_TOKEN_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", text))).strip()


def _years_in(text: str) -> list[int]:
    return sorted({int(y) for y in _YEAR_TOKEN_RE.findall(text)})


async def _fetch_text(url: str, session: httpx.AsyncClient) -> str:
    content, truncated = await download_bytes(url, session=session)
    if truncated:
        raise ValueError(f"La página de {url} superó el límite de descarga.")
    return content.decode("utf-8", errors="replace")


def _new_session() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT})


# --- Shared: Liferay document detail page -> real download link ---

# Matches the "Descargar" action on a document_library_display detail page.
# The icon filename (large/<ext>.png) is the format signal -- reliable
# regardless of whether the URL itself carries a file extension (see module
# docstring: Informes de Auditoría's real links frequently don't).
_DETAIL_DOWNLOAD_RE = re.compile(
    r'<a class="taglib-icon" href="(?P<url>https://www\.iess\.gob\.ec/documents/10162/[^"]+)"'
    r' target="_blank" title="\(Abre una nueva ventana\)"\s*>\s*'
    r'<img class="icon" src="[^"]*/file_system/large/(?P<ext>\w+)\.png"'
)

_TOTAL_RESULTS_RE = re.compile(
    r"el intervalo\s+\d+\s*-\s*\d+\s+de\s+(?P<total>\d+)\s+resultados"
)


def _parse_detail_download(html: str) -> tuple[str, str] | None:
    m = _DETAIL_DOWNLOAD_RE.search(html)
    if m is None:
        return None
    return m.group("url"), m.group("ext").upper()


async def _resolve_detail_links(
    entries: list[dict[str, Any]],
    detail_url_of: Any,
    session: httpx.AsyncClient,
) -> None:
    """Fetch each entry's Liferay detail page and fill in "url"/"formato" in
    place, bounded by _DETAIL_CONCURRENCY. Entries whose detail page can't
    be parsed keep url=None/formato="DESCONOCIDO" rather than being dropped
    -- callers should still see that the document exists."""
    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def resolve_one(entry: dict[str, Any]) -> None:
        async with semaphore:
            try:
                html = await _fetch_text(detail_url_of(entry), session)
            except (ValueError, httpx.HTTPError) as exc:
                logger.warning("No se pudo leer la página de detalle de IESS: %s", exc)
                entry["url"] = None
                entry["formato"] = "DESCONOCIDO"
                return
            parsed = _parse_detail_download(html)
            if parsed is None:
                entry["url"] = None
                entry["formato"] = "DESCONOCIDO"
            else:
                entry["url"], entry["formato"] = parsed

    await asyncio.gather(*(resolve_one(e) for e in entries))


# --- Boletines Estadísticos ---

_BOL_ROW_RE = re.compile(
    rf'document_library_display/{_BOL_PORTLET}/view/{_BOL_ROOT}/(?P<doc_id>\d+)[^"]*">\s*'
    r'<span[^>]*>\s*<img[^>]*/>\s*<span class="taglib-text">(?P<title>[^<]*)</span>'
)


def _bol_detail_url(doc_id: str) -> str:
    return f"{_BOL_LIST_URL}/-/document_library_display/{_BOL_PORTLET}/view/{_BOL_ROOT}/{doc_id}"


async def _fetch_boletines() -> list[dict[str, Any]]:
    cached = _boletines_cache.get("boletines")
    if cached is not None:
        return cached

    async with _boletines_lock:
        cached = _boletines_cache.get("boletines")
        if cached is not None:
            return cached

        logger.info("Descargando el índice de Boletines Estadísticos de IESS")
        async with _new_session() as session:
            html = await _fetch_text(_BOL_LIST_URL, session)
            total_m = _TOTAL_RESULTS_RE.search(html)
            pages = 1
            if total_m:
                pages = max(1, -(-int(total_m.group("total")) // 20))

            htmls = [html]
            if pages > 1:
                # Unlike the "-/document_library_display/..." friendly URLs
                # used for a single document/folder's own page (which embed
                # the portlet id in the path and accept a bare cur2/delta2
                # query), this plain query-string-routed page needs the
                # full Liferay p_p_id/p_p_lifecycle/... routing params too
                # -- confirmed live: cur2 alone silently re-served page 1.
                more = await asyncio.gather(
                    *(
                        _fetch_text(
                            f"{_BOL_LIST_URL}?p_p_id=110_INSTANCE_{_BOL_PORTLET}"
                            f"&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
                            f"&p_p_col_id=column-1&p_p_col_pos=1&p_p_col_count=3"
                            f"&_110_INSTANCE_{_BOL_PORTLET}_cur2={p}"
                            f"&_110_INSTANCE_{_BOL_PORTLET}_delta2=20",
                            session,
                        )
                        for p in range(2, pages + 1)
                    )
                )
                htmls.extend(more)

            seen: dict[str, str] = {}
            for page_html in htmls:
                for m in _BOL_ROW_RE.finditer(page_html):
                    seen.setdefault(m.group("doc_id"), _clean(m.group("title")))

            boletines = [
                {"id": doc_id, "titulo": titulo, "anios": _years_in(titulo)}
                for doc_id, titulo in seen.items()
            ]
            await _resolve_detail_links(
                boletines, lambda e: _bol_detail_url(e["id"]), session
            )

        if boletines:
            _boletines_cache.set("boletines", boletines)
        return boletines


async def list_boletines(anio: int | None = None, query: str = "") -> dict[str, Any]:
    """
    List IESS's annual Boletines Estadísticos (iess.gob.ec/es/estadisticas),
    resolved to a direct PDF URL each.

    Args:
        anio: Only return boletines whose title mentions this year (a
            boletín can cover more than one year, e.g. "2011 2012 2013").
        query: Free text matched (accent-insensitive) against the título.
    """
    boletines = await _fetch_boletines()
    q = _strip(query)
    matched = [
        b
        for b in boletines
        if (anio is None or anio in b["anios"]) and (not q or q in _strip(b["titulo"]))
    ]
    matched.sort(key=lambda b: (b["anios"] or [0])[-1], reverse=True)
    return {
        "total": len(matched),
        "total_en_archivo": len(boletines),
        "source": "IESS — Boletines Estadísticos, iess.gob.ec",
        "url_fuente": _BOL_LIST_URL,
        "boletines": matched,
    }


# --- Estudios Actuariales ---

_ACT_YEAR_LINK_RE = re.compile(
    r'href="(?P<url>https://www\.iess\.gob\.ec/es/web/guest/estudios-actuariales[^"]*)"'
    r'[^>]*class="enlace"[^>]*>Estudios<br\s*/?>\s*Actuariales\s*(?P<anio>\d{4})</a>'
)
# Two link shapes confirmed live on a year page: the Liferay pattern
# (documents/10162/<folder>/<file>, extension optional -- see module
# docstring) and 2010's own static path (informacion/Estudios_Actuariales_
# 2010/<file>.pdf). Neither goes through a Liferay view page first --
# unlike Boletines/Auditoría, these ARE the final links already.
_ACT_DOC_RE = re.compile(
    r'href="(?P<url>/(?:documents/10162|informacion)/[^"]+)"[^>]*>(?P<titulo>[^<]*)</a>'
)
_ACT_GROUP_RE = re.compile(r"<h3[^>]*>([^<]*)</h3>")


def _act_format(url: str) -> str:
    return "PDF" if url.lower().endswith(".pdf") else "PDF (asumido, ver docstring)"


def _parse_actuariales_year_page(html: str, anio: int) -> list[dict[str, Any]]:
    events: list[tuple[int, str, Any]] = []
    for m in _ACT_GROUP_RE.finditer(html):
        events.append((m.start(), "group", _clean(m.group(1))))
    for m in _ACT_DOC_RE.finditer(html):
        events.append((m.start(), "doc", m))
    events.sort(key=lambda e: e[0])

    documentos: list[dict[str, Any]] = []
    seen: set[str] = set()
    grupo: str | None = None
    for _, kind, data in events:
        if kind == "group":
            grupo = data
            continue
        url = (
            f"{_BASE}{data.group('url')}"
            if data.group("url").startswith("/")
            else data.group("url")
        )
        if url in seen:
            continue
        seen.add(url)
        documentos.append(
            {
                "anio": anio,
                "grupo": grupo,
                "titulo": _clean(data.group("titulo")),
                "url": url,
                "formato": _act_format(url),
            }
        )
    return documentos


async def _fetch_actuariales() -> dict[int, list[dict[str, Any]]]:
    cached = _actuariales_cache.get("actuariales")
    if cached is not None:
        return cached

    async with _actuariales_lock:
        cached = _actuariales_cache.get("actuariales")
        if cached is not None:
            return cached

        logger.info("Descargando el índice de Estudios Actuariales de IESS")
        async with _new_session() as session:
            index_html = await _fetch_text(_ACT_INDEX_URL, session)
            year_urls = {
                int(m.group("anio")): m.group("url")
                for m in _ACT_YEAR_LINK_RE.finditer(index_html)
            }

            pages = await asyncio.gather(
                *(_fetch_text(url, session) for url in year_urls.values()),
                return_exceptions=True,
            )

            por_anio: dict[int, list[dict[str, Any]]] = {}
            for anio, page in zip(year_urls.keys(), pages, strict=True):
                if isinstance(page, BaseException):
                    logger.warning(
                        "No se pudo leer Estudios Actuariales %s de IESS: %s",
                        anio,
                        page,
                    )
                    continue
                por_anio[anio] = _parse_actuariales_year_page(page, anio)

        if por_anio:
            _actuariales_cache.set("actuariales", por_anio)
        return por_anio


async def list_estudios_actuariales(
    anio: int | None = None, query: str = ""
) -> dict[str, Any]:
    """
    List IESS's Estudios Actuariales (iess.gob.ec/estudios-actuariales/) —
    actuarial valuation studies per social-security fund (IVM, Salud,
    Riesgos del Trabajo, Seguro Social Campesino, Cesantía, Desempleo).

    The set of available years is discovered live from the index page, not
    hardcoded — IESS has published complete sets for 2010, 2013, 2018, and
    2020 as of this writing, but a year added later would show up here
    without a code change.

    Args:
        anio: Only return documents from this year's set (see años_disponibles
            in the result for what's currently published).
        query: Free text matched (accent-insensitive) against the título or
            grupo (fund name).
    """
    por_anio = await _fetch_actuariales()
    if anio is not None and anio not in por_anio:
        disponibles = ", ".join(str(a) for a in sorted(por_anio)) or "(ninguno)"
        raise ValueError(
            f"No hay Estudios Actuariales para {anio}. Años disponibles: {disponibles}"
        )

    q = _strip(query)
    candidatos = (
        por_anio.get(anio, [])
        if anio is not None
        else [d for docs in por_anio.values() for d in docs]
    )
    matched = [
        d
        for d in candidatos
        if not q or q in _strip(d["titulo"]) or q in _strip(d.get("grupo") or "")
    ]
    matched.sort(key=lambda d: (d["anio"], d["titulo"]), reverse=True)
    return {
        "total": len(matched),
        "anios_disponibles": sorted(por_anio.keys()),
        "source": "IESS — Estudios Actuariales, iess.gob.ec",
        "url_fuente": _ACT_INDEX_URL,
        "documentos": matched,
    }


# --- Informes de Auditoría ---

_AUD_YEAR_ROW_RE = re.compile(
    rf'document_library_display/{_AUD_PORTLET}/view/(?P<folder_id>\d+)\?[^"]*">'
    r'<a[^>]*href="[^"]*"><img[^>]*folder\.png"><strong>(?P<anio>\d{4})</strong></a></a>.*?'
    r"col-3[^>]*>\s*<a[^>]*>(?P<total>\d+)</a>",
    re.DOTALL,
)
_AUD_DOC_ROW_RE_TEMPLATE = (
    r'document_library_display/{portlet}/view/{folder_id}/(?P<doc_id>\d+)[^"]*">\s*'
    r'<span[^>]*>\s*<img[^>]*/>\s*<span class="taglib-text">(?P<titulo>[^<]*)</span>'
    r'(?:\s*</span>\s*<div class="file-entry-list-description">\s*(?P<descripcion>.*?)\s*</div>)?'
)


def _aud_year_detail_url(folder_id: str, doc_id: str) -> str:
    return f"{_AUD_LIST_URL}/-/document_library_display/{_AUD_PORTLET}/view/{folder_id}/{doc_id}"


def _aud_year_folder_url(folder_id: str) -> str:
    return f"{_AUD_LIST_URL}/-/document_library_display/{_AUD_PORTLET}/view/{folder_id}"


async def _fetch_auditoria_anios() -> list[dict[str, Any]]:
    cached = _auditoria_anios_cache.get("anios")
    if cached is not None:
        return cached

    async with _auditoria_anios_lock:
        cached = _auditoria_anios_cache.get("anios")
        if cached is not None:
            return cached

        logger.info(
            "Descargando el índice de Informes de Auditoría de IESS (carpetas por año)"
        )
        seen: dict[str, dict[str, Any]] = {}
        async with _new_session() as session:
            page = 1
            # Confirmed live 2026-09-04: exactly 20 year-folders exist today
            # (2007-2026), the same as this listing's default page size --
            # right at the boundary. Keep fetching while a page returns a
            # full 20 new folders (same "a full page might mean there's
            # more" caution as _resolve_auditoria_anio's known total, just
            # without a known total to check against here), capped well
            # above what decades of one-folder-per-year could plausibly
            # reach.
            while page <= 20:
                url = _AUD_LIST_URL
                if page > 1:
                    url = (
                        f"{_AUD_LIST_URL}?p_p_id=110_INSTANCE_{_AUD_PORTLET}"
                        f"&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
                        f"&p_p_col_id=column-1&p_p_col_pos=1&p_p_col_count=3"
                        f"&_110_INSTANCE_{_AUD_PORTLET}_cur1={page}"
                        f"&_110_INSTANCE_{_AUD_PORTLET}_delta1=20"
                    )
                html = await _fetch_text(url, session)
                new_this_page = 0
                for m in _AUD_YEAR_ROW_RE.finditer(html):
                    if m.group("folder_id") in seen:
                        continue
                    seen[m.group("folder_id")] = {
                        "anio": int(m.group("anio")),
                        "folder_id": m.group("folder_id"),
                        "total_documentos": int(m.group("total")),
                    }
                    new_this_page += 1
                if new_this_page < 20:
                    break
                page += 1

        anios = list(seen.values())
        anios.sort(key=lambda a: a["anio"])
        if anios:
            _auditoria_anios_cache.set("anios", anios)
        return anios


async def list_auditoria_anios() -> dict[str, Any]:
    """
    List IESS's Informes de Auditoría archive's year-folders
    (iess.gob.ec/es/informes-de-auditoria) with each year's document count.
    Call get_auditoria_documentos(anio) to resolve one year's actual
    documents (título, descripción, direct URL).
    """
    anios = await _fetch_auditoria_anios()
    total_documentos = sum(a["total_documentos"] for a in anios)
    return {
        "total_anios": len(anios),
        "total_documentos": total_documentos,
        "source": "IESS — Informes de Auditoría, iess.gob.ec",
        "url_fuente": _AUD_LIST_URL,
        "anios": anios,
    }


async def get_auditoria_documentos(anio: int, query: str = "") -> dict[str, Any]:
    """
    Fetch one Informes de Auditoría year-folder and resolve its documents to
    direct URLs (título, descripción, url, formato).

    A year can hold up to ~42 documents (2009, confirmed live), so this
    fetches the folder's own pages (paginated 20/page) plus one detail-page
    request per document to resolve its real download link -- more requests
    than list_auditoria_anios(), which only reads the index. Results are
    cached per year.

    Args:
        anio: A year from list_auditoria_anios()'s "anios" (2007-2026
            confirmed live as of this writing).
        query: Free text matched (accent-insensitive) against título or
            descripción.
    """
    anios = await _fetch_auditoria_anios()
    match = next((a for a in anios if a["anio"] == anio), None)
    if match is None:
        disponibles = ", ".join(str(a["anio"]) for a in anios) or "(ninguno)"
        raise ValueError(
            f"No hay carpeta de Informes de Auditoría para {anio}. Años disponibles: {disponibles}"
        )

    cache_key = str(anio)
    cached = _auditoria_docs_cache.get(cache_key)
    if cached is None:
        lock = _auditoria_docs_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = _auditoria_docs_cache.get(cache_key)
            if cached is None:
                cached = await _resolve_auditoria_anio(match)
                if cached:
                    _auditoria_docs_cache.set(cache_key, cached)
                elif match["total_documentos"] == 0:
                    # A genuinely empty year (e.g. 2026, not yet populated)
                    # is a valid, cacheable result -- only a *failed* scrape
                    # (total_documentos > 0 but nothing parsed) should be
                    # retried on the next call rather than cached as empty.
                    _auditoria_docs_cache.set(cache_key, cached)

    q = _strip(query)
    documentos = [
        d
        for d in cached
        if not q or q in _strip(d["titulo"]) or q in _strip(d.get("descripcion") or "")
    ]
    return {
        "anio": anio,
        "total": len(documentos),
        "total_en_carpeta": len(cached),
        "source": "IESS — Informes de Auditoría, iess.gob.ec",
        "url_fuente": _aud_year_folder_url(match["folder_id"]),
        "documentos": documentos,
    }


async def _resolve_auditoria_anio(anio_info: dict[str, Any]) -> list[dict[str, Any]]:
    folder_id = anio_info["folder_id"]
    total = anio_info["total_documentos"]
    if total == 0:
        return []

    pages_needed = max(1, -(-total // 20))
    base_url = _aud_year_folder_url(folder_id)
    row_re = re.compile(
        _AUD_DOC_ROW_RE_TEMPLATE.format(portlet=_AUD_PORTLET, folder_id=folder_id)
    )

    logger.info(
        "Descargando %d documento(s) de Informes de Auditoría IESS %s (carpeta %s)",
        total,
        anio_info["anio"],
        folder_id,
    )
    async with _new_session() as session:
        urls = [base_url] + [
            f"{base_url}?_110_INSTANCE_{_AUD_PORTLET}_cur2={p}&_110_INSTANCE_{_AUD_PORTLET}_delta2=20"
            for p in range(2, pages_needed + 1)
        ]
        htmls = await asyncio.gather(*(_fetch_text(u, session) for u in urls))

        seen: dict[str, dict[str, Any]] = {}
        for html in htmls:
            for m in row_re.finditer(html):
                doc_id = m.group("doc_id")
                if doc_id in seen:
                    continue
                seen[doc_id] = {
                    "anio": anio_info["anio"],
                    "id": doc_id,
                    "titulo": _clean(m.group("titulo")),
                    "descripcion": _clean(m.group("descripcion"))
                    if m.group("descripcion")
                    else "",
                }

        documentos = list(seen.values())
        await _resolve_detail_links(
            documentos,
            lambda e: _aud_year_detail_url(folder_id, e["id"]),
            session,
        )

    return documentos

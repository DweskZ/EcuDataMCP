"""Client for the CNE (Consejo Nacional Electoral) "Bases de datos" page
(www.cne.gob.ec/estadisticas/bases-de-datos/): electoral datasets for every
election process from 2002 to 2025.

Live-verified 2026-10-10. The Incapsula challenge that blocked a plain HTTP
client on 2026-09-06 (RESEARCH.md, Decimonovena pasada) is gone: the page, the
AJAX listing below and the file downloads all answer 200 to `httpx` with this
project's own User-Agent, no cookies, no login, no CAPTCHA. The host still
shows a bot-protection script on its pages, so this may come back; a failure
surfaces as an error rather than an empty list.

- The page is WordPress + WP Download Manager (WPDM). Its top-level accordion
  has one entry per election process (19 on the day: Elecciones Generales
  2002 ... Referendum y Consulta Popular 2025). Each process is a WPDM
  category whose `rel` id is `parent` in the listing call below.
- Listing call (what the page's own JS issues, minus the broken loader):
  `GET /?wpdmactask=listsub&parent=<id>&showsub=1&linktpl=link-template-default-wdc
  &__wpdmacn=<nonce>`. The nonce sits in an inline script of the page. A
  wrong nonce answers 200 with the body `-1`. The answer holds the child
  categories (Diccionarios, Organizaciones Politicas, Registro Electoral,
  Resultados; each is one more call) plus the files of that level.
- Files: `<div class="wpdm-link-tpl" data-durl=".../download/<slug>/?wpdmdl=<id>
  &refresh=<token>">` with a "N descargas" and a size label. The `refresh`
  token is not needed: `?wpdmdl=<id>` alone downloads (checked on a
  703 KB results file).
- Downloads are SPSS `.sav` files (checked on registro electoral, resultados
  and diccionarios of several processes: `Content-Type:
  application/octet-stream`, `$FL2 ... IBM SPSS STATISTICS` header), except
  stray PDFs such as the 2002 "Resolucion". The listing does not state the
  format, so `formato` is DESCONOCIDO. The CNE publishes results down to
  parish level (primera vuelta files run 10-77 MB, past the 5 MB cap of the
  preview tools: download the URL directly).

Files are never downloaded here, only listed.
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
from helpers.text_utils import strip_accents

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.cne.gob.ec"
_PAGE_URL = f"{_BASE}/estadisticas/bases-de-datos/"
_LISTSUB_URL = (
    f"{_BASE}/?wpdmactask=listsub&orderby=date&order=DESC&acccount=1&sac=default"
    "&linktpl=link-template-default-wdc&showsub=1&__wpdmacn={nonce}&parent={parent}"
)
_MAX_PAGE_BYTES = 2_000_000
_MAX_DEPTH = 3

# The process list and nonce change only when a process is added or the
# nonce rotates; keep it short so a rotated nonce heals itself.
_index_cache = TtlCache(ttl_seconds=1800.0, max_entries=1)
# One crawl per process is 5 requests; results change a few times a year.
_files_cache = TtlCache(ttl_seconds=21600.0, max_entries=64)
_fetch_lock = asyncio.Lock()

_TAG_RE = re.compile(r"<[^>]+>")
_NONCE_RE = re.compile(r"__wpdmacn=([a-zA-Z0-9]+)")
_HANDLE_RE = re.compile(
    r'<a[^>]*class="accord-handle"[^>]*rel="(?P<id>\d+)"[^>]*>(?P<name>.*?)</a>', re.DOTALL
)
_FILE_RE = re.compile(
    r'<div class="wpdm-link-tpl[^"]*"[^>]*data-durl="(?P<url>[^"]+)"[^>]*>'
    r'.*?<strong class="ptitle">(?P<title>.*?)</strong>',
    re.DOTALL,
)
_DESCARGAS_RE = re.compile(r"([\d.,]+)\s+descargas", re.IGNORECASE)
_SIZE_RE = re.compile(r"([\d.,]+\s*[KMG]?B)\b", re.IGNORECASE)
_REFRESH_RE = re.compile(r"[&?]refresh=[^&]*")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub("", text))).strip()


def _is_cne_url(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() == "www.cne.gob.ec"


def _strip_refresh(url: str) -> str:
    # Drop the per-request token; `?wpdmdl=<id>` alone downloads the file.
    return _REFRESH_RE.sub("", unescape(url))


def _parse_handles(html: str) -> list[dict[str, str]]:
    return [{"id": m.group("id"), "nombre": _clean(m.group("name"))} for m in _HANDLE_RE.finditer(html)]


def _parse_files(html: str) -> list[dict[str, Any]]:
    archivos: list[dict[str, Any]] = []
    for m in _FILE_RE.finditer(html):
        url = _strip_refresh(m.group("url"))
        if not _is_cne_url(url):
            logger.warning("CNE: descartado link con dominio inesperado (%s).", url)
            continue
        raw_title = m.group("title")
        labels = _clean(raw_title)
        # Labels follow the title inside the same <strong>: "Titulo  N descargas  1.2 MB".
        titulo = _clean(re.sub(r"<span.*", "", raw_title, flags=re.DOTALL))
        descargas = _DESCARGAS_RE.search(labels)
        tamano = _SIZE_RE.findall(labels[len(titulo) :])
        archivos.append(
            {
                "titulo": titulo,
                "formato": "DESCONOCIDO",
                "url": url,
                "descargas": int(re.sub(r"\D", "", descargas.group(1))) if descargas else None,
                "tamano": tamano[-1].strip() if tamano else None,
            }
        )
    return archivos


async def _fetch_text(url: str) -> str:
    content, truncated = await download_bytes(url, max_bytes=_MAX_PAGE_BYTES)
    if truncated:
        raise ValueError(f"La respuesta de {url} superó el límite de descarga.")
    return content.decode("utf-8", errors="replace")


async def _load_index(*, force: bool = False) -> dict[str, Any]:
    if not force:
        cached = _index_cache.get("index")
        if cached is not None:
            return cached
    html = await _fetch_text(_PAGE_URL)
    nonce = _NONCE_RE.search(html)
    procesos = _parse_handles(html)
    if nonce is None or not procesos:
        raise ValueError(
            "La página de bases de datos del CNE no trae la lista de procesos "
            "electorales (¿protección anti-bots o cambio de diseño?)."
        )
    index = {"nonce": nonce.group(1), "procesos": procesos}
    _index_cache.set("index", index)
    return index


async def _listsub(parent: str, nonce: str) -> str | None:
    """One WPDM listing call; None when the nonce was rejected (`-1`)."""
    html = await _fetch_text(_LISTSUB_URL.format(nonce=nonce, parent=parent))
    return None if html.strip() == "-1" else html


async def _crawl(
    parent: str, nonce: str, grupo: str | None, depth: int
) -> list[dict[str, Any]] | None:
    html = await _listsub(parent, nonce)
    if html is None:
        return None
    archivos = [{**a, "grupo": grupo} for a in _parse_files(html)]
    if depth >= _MAX_DEPTH:
        return archivos
    subs = _parse_handles(html)
    results = await asyncio.gather(
        *(_crawl(s["id"], nonce, s["nombre"], depth + 1) for s in subs)
    )
    for sub_files in results:
        if sub_files is None:
            return None
        archivos.extend(sub_files)
    return archivos


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(text)).strip()


def _resolve(procesos: list[dict[str, str]], seccion: str) -> dict[str, str]:
    wanted = _normalize(str(seccion))
    for p in procesos:
        if p["id"] == wanted or _normalize(p["nombre"]) == wanted:
            return p
    partial = [p for p in procesos if wanted and wanted in _normalize(p["nombre"])]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        names = "; ".join(f"{p['id']} = {p['nombre']}" for p in partial)
        raise ValueError(f"'{seccion}' coincide con varios procesos electorales: {names}")
    valid = "; ".join(f"{p['id']} = {p['nombre']}" for p in procesos)
    raise ValueError(f"Proceso electoral '{seccion}' no reconocido. Válidos: {valid}")


async def list_procesos() -> dict[str, Any]:
    """The election processes (WPDM categories) listed on the CNE page."""
    index = await _load_index()
    return {
        "url_fuente": _PAGE_URL,
        "categorias": [dict(p) for p in index["procesos"]],
    }


async def get_proceso_archivos(seccion: str) -> dict[str, Any]:
    """
    List the files of one election process: dictionaries, political
    organizations and candidates, electoral roll by parish, and results.

    Args:
        seccion: The process id from list_procesos() (e.g. "8325") or its
            name ("Elecciones Generales 2025"; accent/case-insensitive, a
            unique fragment is enough).
    """
    index = await _load_index()
    proceso = _resolve(index["procesos"], seccion)

    cached = _files_cache.get(proceso["id"])
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _files_cache.get(proceso["id"])
        if cached is not None:
            return cached
        logger.info("Listando archivos del CNE: %s", proceso["nombre"])
        archivos = await _crawl(proceso["id"], index["nonce"], None, 0)
        if archivos is None:
            # Nonce rotated since the index was cached: reload once.
            index = await _load_index(force=True)
            archivos = await _crawl(proceso["id"], index["nonce"], None, 0)
        if archivos is None:
            raise ValueError("El CNE rechazó el token de la página (respuesta '-1').")
        result = {
            "id": proceso["id"],
            "nombre": proceso["nombre"],
            "url": _PAGE_URL,
            "archivos": archivos,
        }
        if archivos:
            _files_cache.set(proceso["id"], result)
        return result

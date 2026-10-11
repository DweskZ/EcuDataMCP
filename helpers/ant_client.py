"""
Siniestros de tránsito (Agencia Nacional de Tránsito, ANT).

ant.gob.ec and ecu911.gob.ec drop the TLS handshake for every client tried
(checked 2026-10-10, see docs/RESEARCH.md § ANT / siniestros de tránsito), so
this client does not scrape them. ANT's crash records reach the public through
two reliable channels, which this module combines:

- INEC "Estadísticas de Transporte" (ANET / ESTRA): quarterly and annual
  "Siniestros de Tránsito" releases built from ANT administrative records,
  with tabulados (XLSX), open-data microdata (ZIP/CSV), dictionary and
  technical note. Found through INEC's WordPress API (inec_client).
- The CKAN national portal: the INEC ANET 2019 siniestros dataset, SPPAT's
  road-death registry (2016-2021) and the ANT organisation's own datasets
  (driver licences, speed excesses; not crash counts).
"""

import asyncio
import logging
import re
from typing import Any

from helpers import ckan_client, inec_client
from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

# INEC posts about crashes: quarterly "Siniestros de Tránsito", the historical
# series and the annual "Estadísticas de Transporte" yearbooks.
_INEC_QUERIES = ("siniestros de tránsito", "estadísticas de transporte")
_INEC_TITLE_RE = re.compile(
    r"siniestro|accidente|estad[ií]sticas de transporte", re.IGNORECASE
)
_CKAN_QUERIES = ("siniestros", "accidentes de tránsito")
_CKAN_TITLE_RE = re.compile(
    r"siniestro|accidente|fallecid|v[ií]ctima|lesionad|exceso|licencia", re.IGNORECASE
)
# CKAN organisation slug of the Agencia Nacional de Tránsito (ANT).
_ANT_ORG = "antec"
_YEAR_RE = re.compile(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)")

# Bounds simultaneous requests to INEC / CKAN within one search.
_CONCURRENCY = 4

_cache = TtlCache(ttl_seconds=3600.0, max_entries=64)

NOTA = (
    "ant.gob.ec y ecu911.gob.ec no aceptan conexiones desde este servidor "
    "(el TLS se corta); las cifras de siniestros de ANT se publican vía INEC "
    "(registros administrativos de ANT) y el portal CKAN. Para el detalle "
    "descarga los archivos con download_resource/preview_resource_data/"
    "read_pdf, o usa get_inec_publicacion_archivos con el id."
)


def _matches(text: str, query: str) -> bool:
    words = [w for w in re.split(r"\s+", query.lower().strip()) if len(w) > 2]
    low = text.lower()
    return all(w in low for w in words)


def _years(text: str) -> set[int]:
    return {int(y) for y in _YEAR_RE.findall(text)}


async def _gather_bounded(coros: list[Any], sem: asyncio.Semaphore) -> list[Any]:
    """Run coroutines sharing `sem` (one bound per search); results stay in
    input order and exceptions come back as values (callers decide)."""

    async def run(coro: Any) -> Any:
        async with sem:
            return await coro

    return await asyncio.gather(*(run(c) for c in coros), return_exceptions=True)


def _raise_first(results: list[Any]) -> None:
    """Fail the whole source on the first error, but let a cancellation through."""
    for r in results:
        if isinstance(r, BaseException):
            raise r


async def _inec_posts(
    query: str, anio: int, limit: int, sem: asyncio.Semaphore
) -> list[dict[str, Any]]:
    posts: dict[int, dict[str, Any]] = {}
    results = await _gather_bounded(
        [inec_client.search_publicaciones(base, limit=100) for base in _INEC_QUERIES], sem
    )
    _raise_first(results)
    for result in results:
        for post in result["publicaciones"]:
            if _INEC_TITLE_RE.search(post["titulo"]):
                posts.setdefault(post["id"], post)
    found = list(posts.values())
    if anio:
        found = [p for p in found if anio in _years(p["titulo"])]
    if query:
        found = [p for p in found if _matches(p["titulo"], query)]
    found.sort(key=lambda p: p["fecha_publicacion"], reverse=True)
    return found[:limit]


async def _ckan_datasets(
    query: str, anio: int, limit: int, sem: asyncio.Semaphore
) -> list[dict[str, Any]]:
    datasets: dict[str, dict[str, Any]] = {}
    queries = (
        [f"{base} {query}".strip() for base in _CKAN_QUERIES] if query else list(_CKAN_QUERIES)
    )
    results = await _gather_bounded(
        [ckan_client.search_datasets(q, rows=30) for q in queries]
        + [ckan_client.search_datasets_by_filter(f"organization:{_ANT_ORG}", rows=50)],
        sem,
    )
    _raise_first(results)
    *search_results, org = results
    for result in search_results:
        for pkg in result.get("results", []):
            if _CKAN_TITLE_RE.search(pkg.get("title", "")):
                datasets.setdefault(pkg["name"], pkg)
    for pkg in org.get("results", []):
        datasets.setdefault(pkg["name"], pkg)
    found = list(datasets.values())
    if anio:
        found = [
            p for p in found if anio in _years(p.get("title", "") + p.get("name", ""))
        ]
    if query:
        found = [p for p in found if _matches(p.get("title", ""), query)]
    return [
        {
            "id": p["name"],
            "titulo": p.get("title", ""),
            "organizacion": (p.get("organization") or {}).get("name", ""),
            "modificado": (p.get("metadata_modified") or "")[:10],
            "recursos": [
                {
                    "nombre": r.get("name", ""),
                    "formato": r.get("format", ""),
                    "url": r.get("url", ""),
                }
                for r in p.get("resources", [])
            ],
        }
        for p in found[:limit]
    ]


async def search_siniestros(
    query: str = "",
    anio: int = 0,
    limit: int = 10,
    con_archivos: int = 2,
) -> dict[str, Any]:
    """
    Find siniestros de tránsito (ANT) releases: INEC quarterly/annual
    publications and CKAN datasets. Each source fails independently; the
    reason is reported in "avisos" and the other source still returns.
    """
    limit = min(max(limit, 1), 30)
    con_archivos = min(max(con_archivos, 0), 5)
    cache_key = (query.lower().strip(), anio, limit, con_archivos)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    sem = asyncio.Semaphore(_CONCURRENCY)
    inec_res, ckan_res = await asyncio.gather(
        _inec_posts(query, anio, limit, sem),
        _ckan_datasets(query, anio, limit, sem),
        return_exceptions=True,
    )
    avisos: list[str] = []
    publicaciones: list[dict[str, Any]] = []
    datasets: list[dict[str, Any]] = []
    if isinstance(inec_res, BaseException):
        logger.warning("ANT/INEC search failed: %s", inec_res)
        avisos.append(f"INEC (ecuadorencifras.gob.ec) no respondió: {inec_res}")
    else:
        publicaciones = inec_res
    if isinstance(ckan_res, BaseException):
        logger.warning("ANT/CKAN search failed: %s", ckan_res)
        avisos.append(f"Portal CKAN no respondió: {ckan_res}")
    else:
        datasets = ckan_res

    # Attach file links to the newest releases only, one request each.
    attach = publicaciones[:con_archivos]
    file_results = await _gather_bounded(
        [inec_client.get_publicacion_files(post["id"]) for post in attach], sem
    )
    for post, files in zip(attach, file_results, strict=True):
        if isinstance(files, asyncio.CancelledError):
            raise files
        if isinstance(files, BaseException):
            avisos.append(f"Sin archivos para la publicación {post['id']}: {files}")
        else:
            post["archivos"] = files.get("archivos", [])

    result = {
        "query": query,
        "anio": anio or None,
        "publicaciones_inec": publicaciones,
        "datasets_ckan": datasets,
        "avisos": avisos,
        "nota": NOTA,
    }
    if not avisos:
        _cache.set(cache_key, result)
    return result

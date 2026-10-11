"""Client for the statistics PDFs and spreadsheets of the Ministerio de
Ambiente y Energía (ex Ministerio de Energía y Minas, ex MERNNR), which
absorbed the hydrocarbons, mining and electricity portfolios.

Hosts, checked live 2026-10-10 from a VPN: `recursosyenergia.gob.ec` and
`arcernnr.gob.ec` do not resolve in DNS, and `controlrecursosyenergia.gob.ec`
only serves a hosting-panel test page over plain HTTP (its HTTPS port refuses
connections), so none of them carries content. The portfolio now lives at
`www.ambienteyenergia.gob.ec`, a WordPress site. It drops connections from
clients without a browser User-Agent, so this client sends one.

The site publishes no statistics index page (`/estadisticas-hidrocarburiferas/`
is an empty legacy shell), but every statistical file sits in the WordPress
media library, whose REST endpoint is public and searchable. Each section
below is the union of a few search terms plus a filename filter, because the
search matches the whole media library (contracts, resumes, press images) and
the filenames are the only reliable signal. Files uploaded straight to the
filesystem never reach the media library and cannot be listed.

This client returns links only. The files are PDFs or XLS/XLSX of several MB;
download them directly or hand the URL to `read_pdf`.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any
from urllib.parse import unquote

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.ambienteyenergia.gob.ec"
_WP_MEDIA_URL = f"{_BASE}/wp-json/wp/v2/media"

# The site closes the connection on non-browser User-Agents.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
_TIMEOUT = 40.0
_ATTEMPTS = 3
_PAGE_SIZE = 100
_MAX_PAGES = 5

_SECCIONES: list[dict[str, Any]] = [
    {
        "id": "estadistica_hidrocarburos",
        "nombre": "Estadística hidrocarburífera (crudo, derivados, resúmenes)",
        "descripcion": (
            "Anuarios de la estadística hidrocarburífera: crudo, derivados y "
            "resúmenes, de 2002 a 2024 con huecos (faltan, por ejemplo, 2012, "
            "2014 y 2017; 2019 es solo el primer semestre), más la matriz de "
            "producción por campo 2024 en XLSX."
        ),
        "terminos": [
            "Hidrocarburifera",
            "Estadistica Crudo",
            "Estadistica Derivados",
            "Estadistica de Hidrocarburos",
            "Estadisticas de Hidrocarburos",
            "Matriz Produccin",
        ],
        "patron": (
            r"estadistic.*(hidrocarb|crudo|derivado)|(hidrocarb|crudo|derivado).*estadistic"
            r"|resumen.*hidrocarb|actividad-hidrocarb|matriz-produc\w*-campo-hidrocarb"
        ),
    },
    {
        "id": "mineria_exportaciones_recaudacion",
        "nombre": "Minería: exportaciones y recaudación tributaria minera",
        "descripcion": (
            "Informes y bases de exportaciones mineras y de recaudación "
            "tributaria del sector minero (indicadores del Plan Nacional de "
            "Desarrollo), con las bases XLS de 2024 y las fichas de indicadores."
        ),
        "terminos": [
            "exportaciones mineras",
            "recaudacion tributaria",
            "tributaria minera",
            "sector minero",
        ],
        "patron": r"exportaciones-mineras|recauda\w*.*(minera|minero)|(minera|minero).*recauda",
    },
    {
        "id": "mineria_reportes_semanales",
        "nombre": "Minería: reportes semanales 2020-2021",
        "descripcion": (
            "Serie 'Semana N - Reporte Minería' (julio 2020 a julio 2021, con "
            "huecos). No hay reportes posteriores en la biblioteca de medios."
        ),
        "terminos": ["Reporte Mineria", "Reporte Minería"],
        "patron": r"semana-\d+-reporte-mineria",
    },
    {
        "id": "balance_energetico",
        "nombre": "Balance Energético Nacional (BEN)",
        "descripcion": (
            "Balance Energético Nacional de todas las fuentes (petróleo, gas, "
            "electricidad, renovables): informes completos y capítulos de las "
            "ediciones 2018, 2019, 2023, 2024 y 2025, en PDF."
        ),
        "terminos": ["BEN_", "Balance Energetico Nacional", "CAPITULO BEN"],
        "patron": r"(^|[-_])ben[-_]\d|balance.{0,12}energetico.{0,8}nacional",
    },
]
_SECCIONES_BY_ID = {s["id"]: s for s in _SECCIONES}
_PATRONES = {s["id"]: re.compile(s["patron"]) for s in _SECCIONES}

_FIELDS = "id,date,title,source_url,mime_type"
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_KNOWN_FORMATS = {"PDF", "XLS", "XLSX", "CSV", "DOC", "DOCX", "ZIP"}

# New editions land a few times a year; same TTL as the other archive clients.
_archivo_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_fetch_lock = asyncio.Lock()


def _filename(url: str) -> str:
    return unquote(url.rsplit("/", 1)[-1])


def _seccion_of(url: str) -> str | None:
    """Section whose filename filter matches, or None for unrelated media."""
    nombre = strip_accents(_filename(url).rsplit(".", 1)[0]).replace(" ", "-")
    for seccion_id, patron in _PATRONES.items():
        if patron.search(nombre):
            return seccion_id
    return None


def _parse_item(item: dict[str, Any]) -> dict[str, Any]:
    url = item["source_url"]
    nombre = _filename(url)
    ext = nombre.rsplit(".", 1)[-1].upper() if "." in nombre else ""
    years = _YEAR_RE.findall(nombre)
    titulo = html.unescape((item.get("title") or {}).get("rendered") or "")
    return {
        "titulo": titulo or nombre.rsplit(".", 1)[0],
        "url": url,
        "formato": ext if ext in _KNOWN_FORMATS else "DESCONOCIDO",
        # Reference year read from the filename (the first one: a 2024
        # yearbook uploaded in 2025 is named ...-2024_8.12.2025). None when
        # it carries none (BEN_24, weekly reports), never guessed from the
        # upload date.
        "periodo": years[0] if years else None,
        "fecha_subida": item.get("date"),
    }


async def _get_page(
    session: httpx.AsyncClient, term: str, page: int
) -> tuple[list[dict[str, Any]], int]:
    # The site occasionally drops a connection mid-request; these are
    # read-only GETs, so retry on any transport error (not HTTP statuses).
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            resp = await session.get(
                _WP_MEDIA_URL,
                params={
                    "search": term,
                    "per_page": _PAGE_SIZE,
                    "page": page,
                    "_fields": _FIELDS,
                },
            )
            break
        except httpx.TransportError:
            if attempt == _ATTEMPTS:
                raise
            await asyncio.sleep(attempt)
    # WordPress answers 400 for a page past the last one.
    if resp.status_code == 400:
        return [], 0
    resp.raise_for_status()
    return resp.json(), int(resp.headers.get("X-WP-TotalPages", "1"))


async def _fetch_archivo() -> dict[str, list[dict[str, Any]]]:
    cached = _archivo_cache.get("archivo")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _archivo_cache.get("archivo")
        if cached is not None:
            return cached

        por_seccion: dict[str, list[dict[str, Any]]] = {s["id"]: [] for s in _SECCIONES}
        vistos: set[int] = set()
        terminos = dict.fromkeys(t for s in _SECCIONES for t in s["terminos"])
        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
        ) as session:
            for term in terminos:
                logger.info("Buscando estadísticas del Ministerio de Energía: %s", term)
                for page in range(1, _MAX_PAGES + 1):
                    items, total_pages = await _get_page(session, term, page)
                    for item in items:
                        item_id = item.get("id")
                        # Infographics and photos share the same filenames
                        # as the real statistics; keep documents only.
                        if (
                            item_id in vistos
                            or not item.get("source_url")
                            or item.get("mime_type", "").startswith(
                                ("image/", "video/")
                            )
                        ):
                            continue
                        vistos.add(item_id)
                        seccion_id = _seccion_of(item["source_url"])
                        if seccion_id is not None:
                            por_seccion[seccion_id].append(_parse_item(item))
                    if page >= total_pages:
                        break

        for archivos in por_seccion.values():
            archivos.sort(key=lambda a: a["fecha_subida"] or "", reverse=True)
        # Don't cache a fully empty result: it looks like a transient failure.
        if any(por_seccion.values()):
            _archivo_cache.set("archivo", por_seccion)
        return por_seccion


async def list_secciones() -> dict[str, Any]:
    """The fixed sections with the live file count of each."""
    por_seccion = await _fetch_archivo()
    return {
        "total": len(_SECCIONES),
        "url_fuente": _WP_MEDIA_URL,
        "categorias": [
            {
                "id": s["id"],
                "nombre": s["nombre"],
                "total_archivos": len(por_seccion[s["id"]]),
            }
            for s in _SECCIONES
        ],
    }


async def get_seccion_archivos(seccion: str) -> dict[str, Any]:
    """
    Files of one section, newest upload first.

    Args:
        seccion: A section id from list_secciones(); the display name also
            works (accent/case-insensitive).
    """
    wanted = strip_accents(seccion).strip()
    info = _SECCIONES_BY_ID.get(wanted) or next(
        (s for s in _SECCIONES if strip_accents(s["nombre"]) == wanted), None
    )
    if info is None:
        validas = ", ".join(_SECCIONES_BY_ID)
        raise ValueError(f"Sección '{seccion}' no reconocida. Válidas: {validas}")

    por_seccion = await _fetch_archivo()
    return {
        "id": info["id"],
        "nombre": info["nombre"],
        "descripcion": info["descripcion"],
        "url_fuente": _WP_MEDIA_URL,
        "archivos": por_seccion[info["id"]],
    }

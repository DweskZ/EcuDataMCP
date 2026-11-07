"""Monthly tourism bulletins ("Boletín de Cifras del Sector Turismo").

The Ministerio de Turismo merged into Producción in 2025 (Decreto 60) and its
domains stopped resolving; the bulletins moved to
https://www.produccion.gob.ec/boletin-de-cifras-sector-turismo/. That post
links them through URL shorteners (one with broken TLS), so the files are
listed from WordPress's media API instead, which returns each PDF's real URL
(confirmed live 2026-11-07: 12 bulletins, November 2025 to October 2026,
~33 pages each: UN Tourism barometer, arrivals and departures by
nationality, holiday occupancy, protected-area visits, the establishment
register). There is no XLSX or CSV; read_pdf extracts the tables' text.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urlencode

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.text_utils import strip_accents

_SITE = "https://www.produccion.gob.ec"
_POST_URL = f"{_SITE}/boletin-de-cifras-sector-turismo/"
_MEDIA_URL = f"{_SITE}/wp-json/wp/v2/media"
_PER_PAGE = 100
_MAX_PAGES = 5

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_PERIOD_RE = re.compile(r"(" + "|".join(_MESES) + r")[\s_-]*(20\d\d)")

_cache = TtlCache(ttl_seconds=21600.0, max_entries=1, persist="turismo_boletines")


def period_from_title(title: str) -> tuple[int | None, int | None]:
    """(año, mes) of the bulletin, read from its title ("... Octubre 2026")."""
    match = _PERIOD_RE.search(strip_accents(title))
    if not match:
        return None, None
    return int(match.group(2)), _MESES[match.group(1)]


def parse_media(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the bulletin PDFs from a media-API page, newest period first."""
    boletines = []
    seen: set[str] = set()
    for item in items:
        if item.get("mime_type") != "application/pdf":
            continue
        title = html.unescape((item.get("title") or {}).get("rendered") or "")
        plain = strip_accents(title)
        url = item.get("source_url") or ""
        if "boletin" not in plain or "turismo" not in plain or not url or url in seen:
            continue
        seen.add(url)
        anio, mes = period_from_title(title)
        boletines.append(
            {
                "titulo": title,
                "url": url,
                "formato": "PDF",
                "anio": anio,
                "mes": mes,
                "periodo": f"{anio}-{mes:02d}" if anio and mes else None,
                "fecha": str(item.get("date") or "")[:10] or None,
            }
        )
    boletines.sort(key=lambda b: (b["periodo"] or "", b["fecha"] or ""), reverse=True)
    return boletines


async def _fetch_boletines_fresh() -> list[dict[str, Any]]:
    cached = _cache.get("boletines")
    if cached is not None:
        return cached
    items: list[dict[str, Any]] = []
    for page in range(1, _MAX_PAGES + 1):
        query = urlencode(
            {
                "search": "turismo",
                "per_page": _PER_PAGE,
                "page": page,
                "_fields": "date,source_url,mime_type,title",
            }
        )
        raw, truncated = await download_bytes(f"{_MEDIA_URL}?{query}")
        if truncated:
            raise ValueError("La respuesta de la API de medios de produccion.gob.ec superó el límite.")
        batch = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(batch, list):
            raise TypeError("La API de medios de produccion.gob.ec devolvió un formato inesperado.")
        items.extend(batch)
        if len(batch) < _PER_PAGE:
            break
    boletines = parse_media(items)
    if boletines:
        _cache.set("boletines", boletines)
    return boletines


async def _fetch_boletines() -> list[dict[str, Any]]:
    """Fresh fetch, or the last good copy when the source fails (see TtlCache.serve_stale)."""
    try:
        return await _fetch_boletines_fresh()
    except Exception as exc:
        stale = _cache.serve_stale("boletines", exc)
        if stale is None:
            raise
        return stale


async def search_boletines(query: str = "") -> dict[str, Any]:
    """Tourism bulletins, filtered by free text over title and period."""
    boletines = await _fetch_boletines()
    q = strip_accents(query)
    if q:
        boletines = [
            b for b in boletines if q in strip_accents(f"{b['titulo']} {b['periodo'] or ''}")
        ]
    return {
        "source": "Ministerio de Producción — Boletín de Cifras del Sector Turismo",
        "url_fuente": _POST_URL,
        "nota": (
            "Boletines mensuales en PDF (~33 páginas): llegadas y salidas por "
            "nacionalidad, ocupación en feriados, áreas protegidas y catastro. Sin "
            "XLSX/CSV; usa read_pdf para extraer las tablas."
        ),
        "archivos": boletines,
    }

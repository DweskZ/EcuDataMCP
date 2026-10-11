"""Client for the Bolsa de Valores de Guayaquil (bolsadevaloresguayaquil.com).

The home page links the exchange's public statistics workbooks directly, no
login and no JS needed (confirmed live 2026-10-10 with this project's own
User-Agent). They sit in four groups, which are this client's sections:

- `historicos`: negotiations since 2019 (`/boletines/historicos/BVG_*.xlsx`):
  Acciones, Obligaciones, Papel comercial, Titularizaciones (the page also
  links it as "VTC"), Bonos del Estado, Notas de crédito and Cetes. One sheet
  ("Base") of one row per trade, dates as Excel serials. Acciones alone is ~32,000 rows / 1.4 MB.
- `dividendos`: `dividendos-totales.xlsx`, dividends paid by share issuers
  since 2002, one sheet per issuer; the first sheet's name states the cut-off
  ("Acciones - Al 31 Julio 2026").
- `valoracion`: `valores-permitidos.xlsx`, the list of securities allowed for
  repo operations ("VIGENTE PARA OCTUBRE 2026").
- `ofertas_publicas`: two .xls files built from Decevale data: securities in
  circulation (sheet names carry the cut-off, "vigentes 31-08-2026") and
  public offers with remaining balance ("SALDO DISPONIBLE AL 08/10/2026").

Section files are scraped from the home page rather than hardcoded, so a new
workbook the exchange adds under the same paths shows up. Freshness comes
from each file's HTTP `Last-Modified` (see helpers/bolsas_common.py); the
`historicos` files were rebuilt on 2026-10-08, the trading day of their last
row (Excel serial 46303), while `dividendos-totales.xlsx` dates from
2026-08-05. Links and metadata only: nothing is downloaded here.

Caveat: openpyxl (what `preview_resource_data` uses for .xlsx) rejects the
BVG workbooks' stylesheet ("Colors must be aRGB hex values"), so previewing
them through that tool fails. Download the URL and read it with a tool that
ignores styles.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

from helpers.bolsas_common import (
    KeyedLocks,
    fetch_html,
    formato_from_url,
    probe_archivos,
)
from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.bolsadevaloresguayaquil.com"
_HOST = "bolsadevaloresguayaquil.com"
_FUENTE = "Bolsa de Valores de Guayaquil, bolsadevaloresguayaquil.com"

_SECCIONES: list[dict[str, str]] = [
    {
        "seccion": "historicos",
        "nombre": "Negociaciones históricas (desde 2019)",
        "url": f"{_BASE}/",
        "prefijo": "/boletines/historicos/BVG_",
    },
    {
        "seccion": "dividendos",
        "nombre": "Dividendos entregados (desde 2002)",
        "url": f"{_BASE}/",
        "prefijo": "/boletines/historicos/dividendos",
    },
    {
        "seccion": "valoracion",
        "nombre": "Valores permitidos (reporto)",
        "url": f"{_BASE}/",
        "prefijo": "/boletines/valoracion/",
    },
    {
        "seccion": "ofertas_publicas",
        "nombre": "Ofertas públicas: en circulación y saldos",
        "url": f"{_BASE}/",
        "prefijo": "/ofertas-publicas/files/",
    },
]
_SECCIONES_BY_KEY = {s["seccion"]: s for s in _SECCIONES}

# The files change at most daily; one cache slot per section plus the page.
_page_cache = TtlCache(ttl_seconds=3600.0, max_entries=1)
_seccion_cache = TtlCache(ttl_seconds=3600.0, max_entries=len(_SECCIONES))
# Per-section locks: a slow probe of one section does not block the others;
# the home page (shared by all sections) has its own lock.
_seccion_locks = KeyedLocks()
_home_lock = asyncio.Lock()

_TAG_RE = re.compile(r"<[^>]+>")
_LINK_RE = re.compile(
    r'<a\b[^>]*href="(?P<path>/(?:boletines|ofertas-publicas)/[^"]+\.xlsx?)"[^>]*>'
    r"(?P<label>.*?)</a>",
    re.DOTALL | re.IGNORECASE,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub(" ", text)).replace("\xa0", " ")).strip()


def _is_bvg_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == _HOST or host.endswith("." + _HOST)


def list_secciones() -> list[dict[str, str]]:
    """The four fixed BVG file groups (see module docstring)."""
    return [{k: v for k, v in s.items() if k != "prefijo"} for s in _SECCIONES]


def _parse_archivos(html: str, prefijo: str) -> list[dict[str, Any]]:
    archivos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _LINK_RE.finditer(html):
        path = m.group("path")
        if not path.startswith(prefijo) or path in seen:
            continue
        label = _clean(m.group("label"))
        if not label:
            continue  # the page links some files twice; keep the first, labelled one
        seen.add(path)
        url = f"{_BASE}{path}"
        archivos.append(
            {"titulo": label, "url": url, "formato": formato_from_url(url)}
        )
    return archivos


async def _fetch_home() -> str:
    cached = _page_cache.get("html")
    if cached is not None:
        return cached
    async with _home_lock:
        cached = _page_cache.get("html")
        if cached is not None:
            return cached
        logger.info("Descargando la página de inicio de la BVG (%s)", _BASE)
        html = await fetch_html(f"{_BASE}/")
        if _LINK_RE.search(html):
            # Don't cache a maintenance page that has no file links at all.
            _page_cache.set("html", html)
        return html


async def get_seccion_archivos(seccion: str) -> dict[str, Any]:
    """
    List one BVG file group with each file's last-modified date and size.

    Args:
        seccion: One of the keys from list_secciones() ("historicos",
            "dividendos", "valoracion", "ofertas_publicas").
    """
    info = _SECCIONES_BY_KEY.get(seccion)
    if info is None:
        valid = ", ".join(sorted(_SECCIONES_BY_KEY))
        raise ValueError(f"Sección '{seccion}' no reconocida. Válidas: {valid}")

    cached = _seccion_cache.get(seccion)
    if cached is not None:
        return cached

    async with _seccion_locks[seccion]:
        cached = _seccion_cache.get(seccion)
        if cached is not None:
            return cached

        archivos = _parse_archivos(await _fetch_home(), info["prefijo"])
        archivos = [a for a in archivos if _is_bvg_url(a["url"])]
        await probe_archivos(archivos)
        result = {
            "seccion": seccion,
            "nombre": info["nombre"],
            "url": info["url"],
            "source": _FUENTE,
            "total": len(archivos),
            "archivos": archivos,
        }
        if archivos:
            _seccion_cache.set(seccion, result)
        return result

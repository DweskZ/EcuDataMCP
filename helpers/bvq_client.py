"""Client for the Bolsa de Valores de Quito (bolsadequito.com).

The public "Estadísticas" section of this Joomla site links ~45 XLS/XLSX/PDF
statistics files, no login needed (confirmed live 2026-10-10). Two
observations from the probe:

- The initial HTTP 406 reported for a bare `curl` was not reproduced: the
  site answered 200 to plain curl, to a browser User-Agent and to this
  project's own User-Agent, on pages and on files (it sits behind
  Cloudflare, which may reject some clients intermittently). It does answer
  HEAD with an empty reply, so freshness uses a ranged GET
  (helpers/bolsas_common.py).
- The download buttons carry no text: the labels are CSS background images,
  so `titulo` here is derived from the file name ("notas-credito.xls" ->
  "Notas credito"), not copied from the page.

Sections (each is one or more pages whose file links are scraped live):
`cotizaciones_historicas` (negotiations per instrument: acciones, bonos,
cetes, cupones, facturas comerciales, notas de crédito, obligaciones, OCAs,
papel comercial, TBC, titularizaciones, valores genéricos, VTP), `emisiones`, `renta_variable`, `sector_publico`,
`boletines_cierre` (end-of-day bulletins: boletín diario, máximos y mínimos,
ofertas y demandas, repo list, Ecuindex), `boletines_semanales`,
`boletines_valores` (per-instrument bulletins), `analisis_sensibilidad`
(PDF), `valoracion` (daily/monthly price vectors, national equity prices,
spot curve) and `emisores` (registry of issuers and securities).

Freshness differs by file, which is why each entry carries `modificado`:
on 2026-10-10 the cotizaciones, daily bulletins and valoración files were
rebuilt on 2026-10-08 (the vector de precios' valuation date, Excel serial
46303, is 2026-10-08), `boletines_valores` on 2026-09-10, and
`emisiones/facturas-comerciales.xls` on 2024-09-10 (its sheets stop at 2023).

Excluded on purpose: the "Infolab BVQ" bulletins (their pages carry no
files; the content lives behind bvqinfolab.com's login), and the live
"ofertas y demandas" / "operaciones cerradas" market screens (not downloads).
Several files sit near the 5 MB preview cap (cotizaciones bonos.xls 4.3 MB,
the renta-variable bulletin 4.7 MB): download the URL directly.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import unquote, urlparse

from helpers.bolsas_common import (
    KeyedLocks,
    fetch_html,
    formato_from_url,
    probe_archivos,
)
from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://www.bolsadequito.com"
_HOST = "bolsadequito.com"
_FUENTE = "Bolsa de Valores de Quito, bolsadequito.com"
_EST = f"{_BASE}/index.php/estadisticas"

_SECCIONES: list[dict[str, Any]] = [
    {
        "seccion": "cotizaciones_historicas",
        "nombre": "Cotizaciones históricas por instrumento",
        "paginas": [f"{_EST}/boletines-2/cotizaciones-historicas"],
    },
    {
        "seccion": "emisiones",
        "nombre": "Emisiones (renta fija, renta variable, facturas comerciales)",
        "paginas": [f"{_EST}/boletines-2/emisiones"],
    },
    {
        "seccion": "renta_variable",
        "nombre": "Renta variable (dividendos, precios, montos, indicadores)",
        "paginas": [f"{_EST}/boletines-2/renta-variable"],
    },
    {
        "seccion": "sector_publico",
        "nombre": "Negociaciones del sector público",
        "paginas": [f"{_EST}/boletines-2/sector-publico"],
    },
    {
        "seccion": "boletines_cierre",
        "nombre": "Boletines al cierre e información continua",
        "paginas": [f"{_EST}/boletines/boletines-al-cierre"],
    },
    {
        "seccion": "boletines_semanales",
        "nombre": "Boletines semanales",
        "paginas": [f"{_EST}/boletines/boletines-semanales"],
    },
    {
        "seccion": "boletines_valores",
        "nombre": "Boletines por tipo de valor",
        "paginas": [f"{_EST}/boletines/boletines-valores"],
    },
    {
        "seccion": "analisis_sensibilidad",
        "nombre": "Análisis de sensibilidad (PDF mensual)",
        "paginas": [f"{_EST}/boletines/analisis-de-sensibilidad"],
    },
    {
        "seccion": "valoracion",
        "nombre": "Valoración: vectores de precios, precios de renta variable, curva spot",
        "paginas": [
            f"{_EST}/valoracion/vector-de-precios-diario",
            f"{_EST}/valoracion/vector-de-precios-mensual",
            f"{_EST}/valoracion/precio-nacional-renta-variable-diario",
            f"{_EST}/valoracion/precio-nacional-renta-variable-mensual",
            f"{_EST}/valoracion/tasa-spot",
        ],
    },
    {
        "seccion": "emisores",
        "nombre": "Registro de emisores y valores inscritos",
        "paginas": [f"{_BASE}/index.php/mercados-bursatiles/emisores/listado-de-emisores"],
    },
]
_SECCIONES_BY_KEY = {s["seccion"]: s for s in _SECCIONES}

_seccion_cache = TtlCache(ttl_seconds=3600.0, max_entries=len(_SECCIONES))
# Per-section locks: a slow section does not block the others.
_seccion_locks = KeyedLocks()

# Hrefs are absolute on most pages and site-relative on the valoración and
# emisores pages. Normativa and marketing PDFs live under other prefixes and
# are deliberately not matched.
_LINK_RE = re.compile(
    r'href="(?P<url>(?:https://www\.bolsadequito\.com)?/uploads/'
    r'(?:estadisticas|mercados)/[^"]+\.(?:xlsx?|pdf))"',
    re.IGNORECASE,
)


def _is_bvq_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == _HOST or host.endswith("." + _HOST)


def _titulo_from_url(url: str) -> str:
    stem = unquote(url.rsplit("/", 1)[-1]).rsplit(".", 1)[0]
    text = re.sub(r"[-_]+", " ", stem).strip()
    return text[:1].upper() + text[1:]


def list_secciones() -> list[dict[str, str]]:
    """The fixed BVQ statistics sections (see module docstring)."""
    return [
        {"seccion": s["seccion"], "nombre": s["nombre"], "url": s["paginas"][0]}
        for s in _SECCIONES
    ]


def _parse_archivos(html: str, pagina: str) -> list[dict[str, Any]]:
    archivos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _LINK_RE.finditer(html):
        raw = m.group("url")
        url = raw if raw.startswith("http") else f"{_BASE}{raw}"
        if url in seen or not _is_bvq_url(url):
            continue
        seen.add(url)
        archivos.append(
            {
                "titulo": _titulo_from_url(url),
                "url": url,
                "formato": formato_from_url(url),
                "pagina": pagina,
            }
        )
    return archivos


async def get_seccion_archivos(seccion: str) -> dict[str, Any]:
    """
    List one BVQ statistics section with each file's last-modified date and
    size.

    Args:
        seccion: One of the keys from list_secciones().
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

        logger.info("Descargando páginas de la BVQ: %s", seccion)
        pages = await asyncio.gather(*(fetch_html(p) for p in info["paginas"]))
        archivos: list[dict[str, Any]] = []
        seen: set[str] = set()
        for pagina, html in zip(info["paginas"], pages, strict=True):
            for a in _parse_archivos(html, pagina):
                if a["url"] not in seen:
                    seen.add(a["url"])
                    archivos.append(a)
        await probe_archivos(archivos)
        result = {
            "seccion": seccion,
            "nombre": info["nombre"],
            "url": info["paginas"][0],
            "source": _FUENTE,
            "total": len(archivos),
            "archivos": archivos,
        }
        if archivos:
            _seccion_cache.set(seccion, result)
        return result

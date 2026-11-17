"""Monthly publications of two private trade associations.

- FEDEXPOR (Federación Ecuatoriana de Exportadores), "Reporte Estadístico
  Expordata": a monthly foreign-trade report, the trade detail SENAE does
  not publish openly. The page lists each edition as a Google Drive link
  (16 when checked 2026-11-07, January 2026 to October 2026 plus specials).
  The PDFs are ~30 MB, past the 5 MB read cap, so this returns the links
  and the direct-download form (`uc?export=download&id=`).
- AEADE (Asociación de Empresas Automotrices del Ecuador): the monthly
  vehicle-sales press bulletins (73 through the Simple Download Monitor
  plugin, `?sdm_process_download=1&download_id=`) and the yearly
  "Anuario" PDFs.

Both are scraped from their WordPress pages; each item carries `anio`,
`mes` and `periodo` when the title names a month.
"""

from __future__ import annotations

import html
import re
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import _decode_text, download_bytes
from helpers.text_utils import strip_accents
from helpers.turismo_client import period_from_title

_EXPORDATA_URL = "https://www.fedexpor.com/inteligencia-comercial/reporte-expordata/"
_AEADE_VENTAS_URL = "https://www.aeade.net/boletines-de-prensa-venta-de-vehiculos/"
_AEADE_ANUARIO_URL = "https://www.aeade.net/anuario/"

_DRIVE_RE = re.compile(
    r'<a[^>]+href="https://drive\.google\.com/file/d/([\w-]+)/[^"]*"[^>]*>(.*?)</a>', re.DOTALL
)
_SDM_TITLE_RE = re.compile(r'class="sdm_download_title">(.*?)</div>', re.DOTALL)
_SDM_LINK_RE = re.compile(r'href="([^"]*sdm_process_download=1[^"]*download_id=(\d+)[^"]*)"')
_PDF_LINK_RE = re.compile(r'href="(https://www\.aeade\.net/wp-content/uploads/[^"]+\.pdf)"', re.IGNORECASE)

_cache = TtlCache(ttl_seconds=21600.0, max_entries=4, persist="gremios")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _with_period(item: dict[str, Any]) -> dict[str, Any]:
    anio, mes = period_from_title(item["titulo"])
    if anio is None:
        year = re.search(r"(20\d\d)", item["titulo"])
        anio = int(year.group(1)) if year else None
    return {
        **item,
        "anio": anio,
        "mes": mes,
        "periodo": f"{anio}-{mes:02d}" if anio and mes else (str(anio) if anio else None),
    }


def parse_expordata(page: str) -> list[dict[str, Any]]:
    """Drive-hosted Expordata editions; each id once, with its visible title."""
    seen: dict[str, str] = {}
    for drive_id, inner in _DRIVE_RE.findall(page):
        title = _text(inner)
        if title or drive_id not in seen:
            seen[drive_id] = title or seen.get(drive_id, "")
    items = []
    for drive_id, title in seen.items():
        items.append(
            _with_period(
                {
                    "titulo": title or "Expordata",
                    "url": f"https://drive.google.com/file/d/{drive_id}/view",
                    "descarga_directa": f"https://drive.google.com/uc?export=download&id={drive_id}",
                    "formato": "PDF",
                }
            )
        )
    return items


def parse_aeade_ventas(page: str) -> list[dict[str, Any]]:
    """Pair each Simple Download Monitor title with the first link after it."""
    items = []
    seen: set[str] = set()
    for title_match in _SDM_TITLE_RE.finditer(page):
        link = _SDM_LINK_RE.search(page, title_match.end())
        if not link or link.group(2) in seen:
            continue
        seen.add(link.group(2))
        items.append(
            _with_period(
                {
                    "titulo": _text(title_match.group(1)),
                    "url": html.unescape(link.group(1)),
                    "formato": "PDF",
                    "tipo": "boletin_ventas",
                }
            )
        )
    return items


def parse_aeade_anuarios(page: str) -> list[dict[str, Any]]:
    items = []
    for url in dict.fromkeys(_PDF_LINK_RE.findall(page)):
        name = url.rsplit("/", 1)[-1]
        if "anuario" not in name.lower():
            continue  # the page also links the association's statutes
        items.append(
            _with_period({"titulo": name.rsplit(".", 1)[0].replace("-", " ").replace("_", " "), "url": url, "formato": "PDF", "tipo": "anuario"})
        )
    return items


async def _page(url: str) -> str:
    raw, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(f"La página {url} superó el límite de descarga.")
    return _decode_text(raw)


async def _cached(key: str, build) -> list[dict[str, Any]]:
    cached = _cache.get(key)
    if cached is not None:
        return cached
    try:
        items = await build()
    except Exception as exc:
        stale = _cache.serve_stale(key, exc)
        if stale is None:
            raise
        return stale
    if items:
        _cache.set(key, items)
    return items


def _filter(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = strip_accents(query)
    ordered = sorted(items, key=lambda i: i.get("periodo") or "", reverse=True)
    if not q:
        return ordered
    return [i for i in ordered if q in strip_accents(f"{i['titulo']} {i.get('periodo') or ''} {i.get('tipo') or ''}")]


async def search_expordata(query: str = "") -> dict[str, Any]:
    async def build() -> list[dict[str, Any]]:
        return parse_expordata(await _page(_EXPORDATA_URL))

    return {
        "source": "FEDEXPOR — Reporte Estadístico Expordata",
        "url_fuente": _EXPORDATA_URL,
        "nota": (
            "Informes mensuales de comercio exterior en Google Drive (~30 MB cada uno, "
            "sobre el tope de 5 MB de read_pdf): descárgalos con descarga_directa."
        ),
        "archivos": _filter(await _cached("expordata", build), query),
    }


async def search_aeade(query: str = "") -> dict[str, Any]:
    async def build() -> list[dict[str, Any]]:
        ventas = parse_aeade_ventas(await _page(_AEADE_VENTAS_URL))
        anuarios = parse_aeade_anuarios(await _page(_AEADE_ANUARIO_URL))
        return ventas + anuarios

    return {
        "source": "AEADE — boletines de ventas de vehículos y anuarios",
        "url_fuente": _AEADE_VENTAS_URL,
        "nota": (
            "tipo boletin_ventas: ventas mensuales de vehículos (PDF); tipo anuario: "
            "anuario del sector automotor. Escribe 'anuario' en query para ver solo los anuarios."
        ),
        "archivos": _filter(await _cached("aeade", build), query),
    }

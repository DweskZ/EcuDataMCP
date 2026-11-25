"""SNI's "Banco de evaluaciones": evaluations of Ecuador's public interventions.

The Sistema Nacional de Información (sni.gob.ec, Secretaría Nacional de
Planificación) keeps a bank of the evaluations it publishes, as one static
TablePress table inside a WordPress page
(`/informacion-para-la-planificacion/informacion-estadistica/banco-de-evaluaciones/`).
Read live 2026-11-24, no login: 108 rows, 2011 to 2026 (the 2017, 2022-2024
years hold most). Each row names the sector, the entity that ran the
intervention, the entity that evaluated it, the evaluation type, the
intervention, the year of issue, the objective and a link to the report
(104 PDF, three .rar and one .zip). Reports can be read with read_pdf.

Only this table is cataloged. SNI's other sections (population projections,
statistical inventories, technical and normative documents) are Divi Machine
"load more" lists that page through admin-ajax.php with a per-page nonce, so
the HTML carries only their first three or four items; the WordPress media API
(`/wp-json/wp/v2/media`) lists 716 attachments but most spreadsheets were never
uploaded to the media library. See docs/RESEARCH.md § Cuadragésima sexta pasada.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.text_utils import strip_accents as _strip

_SITE = "https://www.sni.gob.ec/"
_PAGE_URL = (
    f"{_SITE}informacion-para-la-planificacion/informacion-estadistica/banco-de-evaluaciones/"
)

_TABLE_RE = re.compile(r'<table[^>]*id="tablepress-1".*?</table>', re.DOTALL)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_HREF_RE = re.compile(r'href="([^"]+)"')
_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")

_cache = TtlCache(ttl_seconds=21600.0, max_entries=1, persist="sni_evaluaciones")


def _text(cell: str) -> str:
    plain = _TAG_RE.sub(" ", _BREAK_RE.sub(" ", cell))
    return re.sub(r"\s+", " ", html.unescape(plain)).strip()


def parse_evaluaciones(page: bytes) -> list[dict[str, Any]]:
    """Banco de evaluaciones table → one entry per row that links a report."""
    table = _TABLE_RE.search(page.decode("utf-8", errors="replace"))
    if table is None:
        return []
    entries = []
    for row in _ROW_RE.findall(table.group(0)):
        cells = _CELL_RE.findall(row)
        if len(cells) < 9:
            continue
        href = _HREF_RE.search(cells[8])
        if href is None:
            continue
        url = urljoin(_SITE, html.unescape(href.group(1)))
        year = _text(cells[6])
        number = _text(cells[0])
        entries.append(
            {
                "titulo": _text(cells[5]),
                "url": url,
                "formato": url.rsplit(".", 1)[-1].upper() if "." in url.rsplit("/", 1)[-1] else None,
                "nro": int(number) if number.isdigit() else None,
                "anio": int(year) if year.isdigit() else None,
                "categoria": _text(cells[1]),
                "entidad_ejecutora": _text(cells[2]),
                "entidad_evaluadora": _text(cells[3]),
                "tipo": _text(cells[4]),
                "objetivo": _text(cells[7]),
            }
        )
    entries.sort(key=lambda e: (-(e["anio"] or 0), e["nro"] or 0))
    return entries


async def _fetch_evaluaciones_fresh() -> list[dict[str, Any]]:
    cached = _cache.get("evaluaciones")
    if cached is not None:
        return cached
    raw, truncated = await download_bytes(_PAGE_URL)
    if truncated:
        raise ValueError("La página del Banco de evaluaciones del SNI superó el límite de descarga.")
    entries = parse_evaluaciones(raw)
    if entries:
        _cache.set("evaluaciones", entries)
    return entries


async def _fetch_evaluaciones() -> list[dict[str, Any]]:
    """Fresh fetch, or the last good copy when the source fails (see TtlCache.serve_stale)."""
    try:
        return await _fetch_evaluaciones_fresh()
    except Exception as exc:
        stale = _cache.serve_stale("evaluaciones", exc)
        if stale is None:
            raise
        return stale


async def search_evaluaciones(query: str = "") -> dict[str, Any]:
    """Evaluation reports matching ``query`` (accent-insensitive, every word must appear)."""
    entries = await _fetch_evaluaciones()
    words = _strip(query).split()
    matched = [
        e
        for e in entries
        if all(
            word
            in _strip(
                " ".join(
                    str(e[k] or "")
                    for k in (
                        "titulo",
                        "categoria",
                        "entidad_ejecutora",
                        "entidad_evaluadora",
                        "tipo",
                        "anio",
                        "objetivo",
                    )
                )
            )
            for word in words
        )
    ]
    return {
        "source": "SNI — Banco de evaluaciones de intervenciones públicas",
        "url_fuente": _PAGE_URL,
        "nota": (
            "Informes de evaluación de programas y proyectos públicos publicados por el SNI "
            f"({len(entries)} en el banco): sector, entidad ejecutora y evaluadora, tipo, año y "
            "objetivo. La mayoría son PDF (read_pdf los lee); unos pocos son .rar o .zip. "
            "Las demás secciones del SNI (proyecciones de población, inventarios, normativa) "
            "cargan por AJAX y no están catalogadas."
        ),
        "archivos": matched,
    }

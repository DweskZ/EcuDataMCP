"""Client for CENACE's "Boletín y Estadística Mensual de Transacciones
Comerciales", documented in docs/RESEARCH.md § CENACE — boletín mensual
legible sin flipbook (Trigésimo quinta pasada).

CENACE publishes each monthly issue only as a FlipHTML5 flipbook (page
images, no PDF: `publication.pdf` is 404 and the download button is off).
Two static files make it readable without a browser:

- `cenace.gob.ec/wp-content/plugins/ez-addons/data/boletines.xlsx`, the
  index behind the bulletin page: one row per issue (URL | NOMBRE), January
  2019 onward, each URL an `online.fliphtml5.com/htwhr/<code>/` book.
- `<book>/files/search/search_config.js`, the flipbook's search index:
  `var textForPages = [...]`, one JSON string per page with the page's text,
  tables flattened to space-separated rows ("CNEL - Guayaquil 610.75 ...").

The issues carry what CKAN's `cenace` datasets lack: production by
resource, commercial demand by distributor, average prices in USD¢/kWh and
the international transactions with Colombia and Peru. 2019-2020 books were
served double-gzipped with a UTF-8 BOM in the research pass; the decoder
handles both, though a re-check on 2026-10-26 got them plain.
"""

from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import re
from typing import Any

import openpyxl

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

_INDEX_URL = "https://www.cenace.gob.ec/wp-content/plugins/ez-addons/data/boletines.xlsx"
_PAGE_URL = "https://www.cenace.gob.ec/boletines/"
_BOOK_RE = re.compile(r"^https://online\.fliphtml5\.com/htwhr/(?P<code>[a-z0-9]+)/?$")
_TITLE_RE = re.compile(r"(?P<mes>[A-Z]+)\s+(?P<anio>\d{4})\s*$")
_SPACES_RE = re.compile(r"[ \t]{3,}")

_MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# The index gains one row a month; a published issue never changes.
_index_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_text_cache = TtlCache(ttl_seconds=86400.0, max_entries=24)
_index_lock = asyncio.Lock()


def _parse_index(content: bytes) -> list[dict[str, Any]]:
    """Index rows newest first, each with `mes` as YYYY-MM. Rows whose title
    has no recognizable month/year or whose URL is not a CENACE flipbook are
    dropped (logged), not guessed."""
    sheet = openpyxl.load_workbook(io.BytesIO(content), read_only=True).active
    boletines: list[dict[str, Any]] = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        url, nombre = (row + (None, None))[:2]
        if not url or not nombre:
            continue
        url, nombre = str(url).strip(), " ".join(str(nombre).split())
        book = _BOOK_RE.match(url)
        title = _TITLE_RE.search(_strip(nombre, lower=False).upper())
        mes = _MESES.get(title.group("mes").lower()) if title else None
        if book is None or mes is None:
            logger.warning("CENACE boletines: fila descartada (%s | %s).", url, nombre)
            continue
        boletines.append(
            {
                "mes": f"{title.group('anio')}-{mes:02d}",
                "titulo": nombre,
                "codigo": book.group("code"),
                "url": url if url.endswith("/") else f"{url}/",
            }
        )
    boletines.sort(key=lambda b: b["mes"], reverse=True)
    return boletines


def _parse_pages(content: bytes) -> list[str]:
    """Page texts from a search_config.js body, newlines normalized."""
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    text = content.decode("utf-8-sig")
    start = text.find("textForPages")
    bracket = text.find("[", start)
    if start < 0 or bracket < 0:
        raise ValueError("El índice de texto del boletín no tiene 'textForPages'.")
    pages, _ = json.JSONDecoder().raw_decode(text, bracket)

    # 2019-2020 issues pad columns with long space runs; two spaces keep the
    # column break visible without the padding.
    return [
        "\n".join(
            _SPACES_RE.sub("  ", line.strip()) for line in str(p).replace("\r\n", "\n").split("\n")
        ).strip()
        for p in pages
    ]


async def _fetch_index() -> list[dict[str, Any]]:
    cached = _index_cache.get("index")
    if cached is not None:
        return cached

    async with _index_lock:
        cached = _index_cache.get("index")
        if cached is not None:
            return cached

        content, truncated = await download_bytes(_INDEX_URL)
        if truncated:
            raise ValueError("El índice de boletines de CENACE superó el límite de descarga.")
        boletines = _parse_index(content)
        if boletines:
            _index_cache.set("index", boletines)
        return boletines


async def list_boletines(anio: int | None = None) -> dict[str, Any]:
    """List the monthly bulletins, newest first, optionally for one year."""
    boletines = await _fetch_index()
    if anio is not None:
        boletines = [b for b in boletines if b["mes"].startswith(f"{anio}-")]
    return {
        "total": len(boletines),
        "url_fuente": _PAGE_URL,
        "boletines": boletines,
    }


async def get_boletin(mes: str) -> dict[str, Any]:
    """
    Fetch the text of one monthly bulletin, page by page.

    Args:
        mes: The issue's month as YYYY-MM (e.g. 2026-07), or "ultimo" for
            the newest one.
    """
    boletines = await _fetch_index()
    if not boletines:
        raise ValueError("El índice de boletines de CENACE vino vacío.")
    clave = mes.strip().lower()
    if clave in ("ultimo", "último", "latest"):
        boletin = boletines[0]
    else:
        boletin = next((b for b in boletines if b["mes"] == clave), None)
    if boletin is None:
        raise ValueError(
            f"No hay boletín para '{mes}'. Usa YYYY-MM entre {boletines[-1]['mes']} "
            f"y {boletines[0]['mes']}."
        )

    paginas = _text_cache.get(boletin["codigo"])
    if paginas is None:
        content, truncated = await download_bytes(f"{boletin['url']}files/search/search_config.js")
        if truncated:
            raise ValueError(f"El texto del boletín {boletin['mes']} superó el límite de descarga.")
        paginas = _parse_pages(content)
        _text_cache.set(boletin["codigo"], paginas)

    return {
        **boletin,
        "total_paginas": len(paginas),
        "paginas": [{"pagina": i, "texto": t} for i, t in enumerate(paginas, start=1)],
    }

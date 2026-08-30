"""Client for the BCE's *Información Estadística Mensual* (IEM).

The BCEData API is excellent for a compact set of ready-made time series.
IEM is different: its monthly bulletin pages link to dozens of individual
XLSX tables, including detailed cuts that do not appear in BCEData.  This
module indexes those links live; it deliberately does not guess file paths
from a bulletin number because the BCE occasionally points a new bulletin at
the previous month's directory.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin

from openpyxl import load_workbook

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip

logger = logging.getLogger(MAIN_LOGGER_NAME)

IEM_INDEX_URL = (
    "https://contenido.bce.fin.ec/documentos/informacioneconomica/"
    "PublicacionesGenerales/IndiceIEM.html"
)

_catalog_cache = TtlCache(ttl_seconds=86400.0, max_entries=1)
_bulletins_cache = TtlCache(ttl_seconds=86400.0, max_entries=1)
_bulletin_tables_cache = TtlCache(ttl_seconds=86400.0, max_entries=512)
_fetch_lock = asyncio.Lock()
_bulletin_fetch_lock = asyncio.Lock()
_HISTORY_CONCURRENCY = 12
_LINK_RE = re.compile(
    r'<a\s+[^>]*href=["\'](?P<url>[^"\']+)["\'][^>]*>(?P<label>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_BULLETIN_RE = re.compile(
    r"m(?P<number>\d{4})(?P<month>\d{2})(?P<year>\d{4})\.html$",
    re.IGNORECASE,
)
_TABLE_RE = re.compile(
    r"(?P<name>IEM-(?P<number>\d+[\w-]*)-e)\.xlsx$", re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", text))).strip()


def _parse_bulletins(html: str) -> list[dict[str, Any]]:
    """Extract monthly bulletin pages from the IEM index, newest first."""
    bulletins: list[dict[str, Any]] = []
    for match in _LINK_RE.finditer(html):
        raw_url = unescape(match.group("url"))
        parsed = _BULLETIN_RE.search(raw_url.split("?", 1)[0])
        if parsed is None:
            continue
        bulletins.append(
            {
                "numero": int(parsed.group("number")),
                "mes": int(parsed.group("month")),
                "anio": int(parsed.group("year")),
                "titulo": _clean(match.group("label")),
                "url": urljoin(IEM_INDEX_URL, raw_url),
            }
        )
    return sorted(bulletins, key=lambda item: item["numero"], reverse=True)


def _section_before(html: str, position: int) -> str:
    """Best-effort section label immediately before a table link.

    IEM is hand-authored HTML rather than an API.  The table title is the
    authoritative searchable label; this breadcrumb is only helpful context.
    """
    nearby = _clean(html[max(0, position - 900) : position])
    matches = re.findall(r"(?:^|\s)([1-4](?:\.\d+){0,2}\s+[^\n]+)", nearby)
    return matches[-1].strip() if matches else ""


def _parse_tables(html: str, bulletin: dict[str, Any]) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _LINK_RE.finditer(html):
        raw_url = unescape(match.group("url"))
        filename = raw_url.split("?", 1)[0].rsplit("/", 1)[-1]
        file_match = _TABLE_RE.search(filename)
        if file_match is None:
            continue
        table_id = file_match.group("name").lower()
        if table_id in seen:
            continue
        seen.add(table_id)
        tables.append(
            {
                "table_id": table_id,
                "titulo": _clean(match.group("label")) or table_id,
                "seccion": _section_before(html, match.start()),
                "url": urljoin(bulletin["url"], raw_url),
                "boletin_numero": bulletin["numero"],
                "boletin_mes": bulletin["mes"],
                "boletin_anio": bulletin["anio"],
                "boletin_url": bulletin["url"],
            }
        )
    return tables


async def _fetch_catalog() -> dict[str, Any]:
    """Fetch the current bulletin catalogue (the cheap/default path)."""
    cached = _catalog_cache.get("catalog")
    if cached is not None:
        return cached
    bulletins = await _fetch_bulletins()
    bulletin = bulletins[0]
    tables = await _fetch_tables_for_bulletin(bulletin)
    return _catalog_result(bulletin, tables)


async def _fetch_bulletins() -> list[dict[str, Any]]:
    cached = _bulletins_cache.get("bulletins")
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _bulletins_cache.get("bulletins")
        if cached is not None:
            return cached

        raw_index, truncated = await download_bytes(IEM_INDEX_URL)
        if truncated:
            raise ValueError("El índice IEM del BCE superó el límite de descarga")
        bulletins = _parse_bulletins(raw_index.decode("utf-8", errors="replace"))
        if not bulletins:
            raise ValueError("No se encontraron boletines IEM en el índice del BCE")
        _bulletins_cache.set("bulletins", bulletins)
        return bulletins


async def _fetch_tables_for_bulletin(bulletin: dict[str, Any]) -> list[dict[str, Any]]:
    key = bulletin["numero"]
    cached = _bulletin_tables_cache.get(key)
    if cached is not None:
        return cached

    async with _bulletin_fetch_lock:
        cached = _bulletin_tables_cache.get(key)
        if cached is not None:
            return cached

        raw_bulletin, truncated = await download_bytes(bulletin["url"])
        if truncated:
            raise ValueError("La página del boletín IEM superó el límite de descarga")
        tables = _parse_tables(raw_bulletin.decode("utf-8", errors="replace"), bulletin)
        if not tables:
            raise ValueError(
                f"El boletín IEM {bulletin['numero']} no expuso tablas XLSX individuales"
            )
        _bulletin_tables_cache.set(key, tables)
        return tables


def _catalog_result(
    bulletin: dict[str, Any], tables: list[dict[str, Any]]
) -> dict[str, Any]:
    result = {
        "source": "Banco Central del Ecuador — Información Estadística Mensual",
        "url_fuente": IEM_INDEX_URL,
        "boletin": bulletin,
        "total_tablas": len(tables),
        "tablas": tables,
    }
    _catalog_cache.set("catalog", result)
    logger.info("IEM BCE indexado: boletín %d, %d tablas", bulletin["numero"], len(tables))
    return result


def _within_years(
    bulletin: dict[str, Any], desde_anio: int, hasta_anio: int
) -> bool:
    return (
        (not desde_anio or bulletin["anio"] >= desde_anio)
        and (not hasta_anio or bulletin["anio"] <= hasta_anio)
    )


async def _fetch_historical_tables(
    bulletins: list[dict[str, Any]], desde_anio: int, hasta_anio: int
) -> tuple[list[dict[str, Any]], int]:
    selected_bulletins = [
        bulletin
        for bulletin in bulletins
        if _within_years(bulletin, desde_anio, hasta_anio)
    ]
    if not selected_bulletins:
        raise ValueError("No hay boletines IEM en el rango solicitado")

    semaphore = asyncio.Semaphore(_HISTORY_CONCURRENCY)

    async def fetch(bulletin: dict[str, Any]) -> list[dict[str, Any]]:
        async with semaphore:
            return await _fetch_tables_for_bulletin(bulletin)

    batches = await asyncio.gather(
        *(fetch(b) for b in selected_bulletins), return_exceptions=True
    )
    tables: list[dict[str, Any]] = []
    loaded = 0
    for bulletin, batch in zip(selected_bulletins, batches, strict=True):
        if isinstance(batch, BaseException):
            logger.warning(
                "No se pudo indexar el boletín IEM %d: %s",
                bulletin["numero"],
                batch,
            )
            continue
        loaded += 1
        tables.extend(batch)
    if not tables:
        raise ValueError("Ningún boletín IEM del rango expuso tablas XLSX")
    return tables, loaded


def _merge_historical_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Present one result per table, retaining every bulletin version."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for table in tables:
        grouped.setdefault(table["table_id"], []).append(table)

    merged = []
    for versions in grouped.values():
        versions.sort(key=lambda item: item["boletin_numero"], reverse=True)
        current = dict(versions[0])
        current["versiones"] = [
            {
                "boletin_numero": version["boletin_numero"],
                "boletin_mes": version["boletin_mes"],
                "boletin_anio": version["boletin_anio"],
                "url": version["url"],
            }
            for version in versions
        ]
        current["boletines_disponibles"] = len(versions)
        merged.append(current)
    return sorted(merged, key=lambda item: item["titulo"].lower())


async def search_tables(
    query: str = "",
    limit: int = 20,
    offset: int = 0,
    historico: bool = False,
    desde_anio: int = 0,
    hasta_anio: int = 0,
) -> dict[str, Any]:
    """Search current tables, or versions across the IEM bulletin archive."""
    if desde_anio and hasta_anio and desde_anio > hasta_anio:
        raise ValueError("desde_anio no puede ser mayor que hasta_anio")
    if historico or desde_anio or hasta_anio:
        bulletins = await _fetch_bulletins()
        selected_bulletins = [
            bulletin
            for bulletin in bulletins
            if _within_years(bulletin, desde_anio, hasta_anio)
        ]
        all_tables, loaded_bulletins = await _fetch_historical_tables(
            bulletins, desde_anio, hasta_anio
        )
        tables = _merge_historical_tables(all_tables)
        catalog = {
            "source": "Banco Central del Ecuador — Información Estadística Mensual",
            "url_fuente": IEM_INDEX_URL,
            "boletin": selected_bulletins[0],
            "boletines_consultados": loaded_bulletins,
            "boletines_sin_tablas": len(selected_bulletins) - loaded_bulletins,
            "total_tablas": len(tables),
            "tablas": tables,
        }
    else:
        catalog = await _fetch_catalog()
    q = _strip(query)
    tables = catalog["tablas"]
    matched = [
        table
        for table in tables
        if not q or q in _strip(f"{table['titulo']} {table['seccion']} {table['table_id']}")
    ]
    return {
        **{key: value for key, value in catalog.items() if key != "tablas"},
        "total": len(matched),
        "offset": offset,
        "historico": historico or bool(desde_anio or hasta_anio),
        "tablas": matched[offset : offset + limit],
    }


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _trim_trailing_blanks(row: list[str]) -> list[str]:
    while row and not row[-1]:
        row.pop()
    return row


def _year(value: Any) -> int | None:
    match = re.match(r"\s*(\d{4})", str(value or ""))
    return int(match.group(1)) if match else None


def _selected_columns(
    header: tuple[Any, ...], desde: str, hasta: str
) -> list[tuple[int, str]]:
    start = _year(desde)
    end = _year(hasta)
    if desde and start is None:
        raise ValueError("desde debe ser un año YYYY")
    if hasta and end is None:
        raise ValueError("hasta debe ser un año YYYY")
    if start is not None and end is not None and start > end:
        raise ValueError("desde no puede ser mayor que hasta")

    selected = []
    for index, value in enumerate(header[1:], start=1):
        year = _year(value)
        if year is None or (start is not None and year < start) or (end is not None and year > end):
            continue
        selected.append((index, str(value)))
    return selected


def _extract_wide_series(
    worksheet: Any, desde: str, hasta: str, max_rows: int
) -> dict[str, Any] | None:
    """Read the common IEM shape: periods across columns, series down rows.

    This is verified against IEM-431-e. Other IEM tables can differ, so a
    non-match returns None and the caller gives a layout-preserving preview.
    """
    all_rows = list(worksheet.iter_rows(values_only=True))
    header_index = next(
        (
            index
            for index, row in enumerate(all_rows)
            if row
            and "period" in _strip(str(row[0] or ""))
            and len(_selected_columns(row, "", "")) >= 2
        ),
        None,
    )
    if header_index is None:
        return None

    selected = _selected_columns(all_rows[header_index], desde, hasta)
    if not selected:
        raise ValueError("La tabla no tiene períodos en el rango solicitado")

    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in all_rows[header_index + 1 :]:
        label = str(row[0]).strip() if row and row[0] is not None else ""
        values = [row[index] if index < len(row) else None for index, _ in selected]
        if not label:
            continue
        if not any(value is not None for value in values):
            # A one-cell row names a unit block, such as "Millones de USD".
            current = {"unidad": label, "series": [], "truncada": False}
            blocks.append(current)
            continue
        if current is None:
            # The first row after the period header often says only "Variable".
            continue
        if len(current["series"]) >= max_rows:
            current["truncada"] = True
            continue
        current["series"].append(
            {
                "nombre": label,
                "valores": {
                    period: row[index] if index < len(row) else None
                    for index, period in selected
                },
            }
        )

    blocks = [block for block in blocks if block["series"]]
    if not blocks:
        return None
    return {
        "formato": "series_ancho",
        "periodos": [period for _, period in selected],
        "bloques": blocks,
    }


def _extract_long_table(
    worksheet: Any, desde: str, hasta: str, max_rows: int
) -> dict[str, Any] | None:
    """Read a second common shape: one observation per row.

    This handles tables whose header has columns such as Año/Período,
    Variable and Valor. It keeps the original column names and cell values;
    it does not rename fields because IEM labels are part of the source.
    """
    all_rows = list(worksheet.iter_rows(values_only=True))
    header_index = None
    header: tuple[Any, ...] | None = None
    period_index = None
    for index, row in enumerate(all_rows[:40]):
        names = [_strip(str(value or "")) for value in row]
        candidate_period = next(
            (
                position
                for position, name in enumerate(names)
                if any(token in name for token in ("period", "ano", "fecha"))
            ),
            None,
        )
        nonempty = sum(bool(name) for name in names)
        if candidate_period is not None and nonempty >= 2:
            header_index = index
            header = row
            period_index = candidate_period
            break
    if header_index is None or header is None or period_index is None:
        return None

    start = _year(desde)
    end = _year(hasta)
    if desde and start is None:
        raise ValueError("desde debe ser un año YYYY")
    if hasta and end is None:
        raise ValueError("hasta debe ser un año YYYY")
    if start is not None and end is not None and start > end:
        raise ValueError("desde no puede ser mayor que hasta")

    headers = _trim_trailing_blanks([_cell(value) for value in header])
    rows: list[list[str]] = []
    total_rows = 0
    for raw_row in all_rows[header_index + 1 :]:
        row = [_cell(value) for value in raw_row[: len(headers)]]
        if not any(row):
            continue
        period = _year(raw_row[period_index] if period_index < len(raw_row) else None)
        if period is None:
            continue
        if (start is not None and period < start) or (end is not None and period > end):
            continue
        total_rows += 1
        if len(rows) < max_rows:
            rows.append(_trim_trailing_blanks(row))
    if not rows:
        return None
    return {
        "formato": "tabla_larga",
        "encabezados": headers,
        "filas": rows,
        "filas_totales": total_rows,
        "truncada": total_rows > len(rows),
    }


def _inspect_xlsx(raw: bytes, max_rows: int) -> dict[str, Any]:
    """Return a layout-preserving preview without guessing a universal header.

    Individual IEM tables use different layouts.  Returning the first
    non-empty rows is safer than pretending a title row is always a header;
    dedicated parsers can be added later for high-value tables.
    """
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        sheets = []
        for worksheet in workbook.worksheets:
            rows: list[list[str]] = []
            nonempty_total = 0
            for row in worksheet.iter_rows(values_only=True):
                rendered = _trim_trailing_blanks([_cell(value) for value in row])
                if not any(rendered):
                    continue
                nonempty_total += 1
                if len(rows) < max_rows:
                    rows.append(rendered[:30])
            sheets.append(
                {
                    "nombre": worksheet.title,
                    "vista": rows,
                    "filas_mostradas": len(rows),
                    "truncada": nonempty_total > len(rows),
                }
            )
        return {"hojas": sheets}
    finally:
        workbook.close()


async def get_table(
    table_id: str,
    desde: str = "",
    hasta: str = "",
    max_rows: int = 20,
    boletin_numero: int = 0,
) -> dict[str, Any]:
    """Download one IEM table version and return structured data when safe."""
    if boletin_numero:
        bulletins = await _fetch_bulletins()
        bulletin = next(
            (item for item in bulletins if item["numero"] == boletin_numero), None
        )
        if bulletin is None:
            raise ValueError(f"Boletín IEM '{boletin_numero}' no encontrado")
        tables = await _fetch_tables_for_bulletin(bulletin)
        catalog = {
            "source": "Banco Central del Ecuador — Información Estadística Mensual",
            "url_fuente": IEM_INDEX_URL,
            "boletin": bulletin,
            "total_tablas": len(tables),
            "tablas": tables,
        }
    else:
        catalog = await _fetch_catalog()
    wanted = table_id.strip().lower()
    table = next((item for item in catalog["tablas"] if item["table_id"] == wanted), None)
    if table is None:
        raise ValueError(f"Tabla IEM '{table_id}' no encontrada en el boletín vigente")

    raw, truncated = await download_bytes(table["url"])
    if truncated:
        raise ValueError("La tabla IEM supera el límite seguro de descarga")
    if not raw.startswith(b"PK"):
        raise ValueError("La URL de la tabla IEM no devolvió un archivo XLSX válido")
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        structured = _extract_wide_series(workbook.active, desde, hasta, max_rows)
        if structured is None:
            structured = _extract_long_table(workbook.active, desde, hasta, max_rows)
    finally:
        workbook.close()

    result = {
        "source": "Banco Central del Ecuador — Información Estadística Mensual",
        "tabla": table,
        "archivo_truncado": False,
    }
    if structured is not None:
        return {**result, **structured}
    return {**result, "formato": "vista", **_inspect_xlsx(raw, max_rows=max_rows)}

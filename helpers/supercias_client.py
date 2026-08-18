"""Client for the Superintendencia de Compañías, Valores y Seguros company registry.

Supercías publishes the full "Directorio de Companias" (226k+ companies) as a
single static Excel export, refreshed daily, with no auth or pagination
needed:
https://mercadodevalores.supercias.gob.ec/reportes/excel/directorio_companias.xlsx

That file (~35 MB) can't be parsed with openpyxl's normal `read_only=True`
streaming mode: the worksheet's `<dimension>` tag is wrong (it declares only
"A1" even though the sheet has 226k+ rows), which makes openpyxl's read-only
iterator stop after a single row. A full (non-read-only) load works but takes
roughly a minute for a file this size. Instead, `_parse_xlsx` streams the
worksheet XML directly with `ElementTree.iterparse`, which is correct
regardless of the bad dimension tag and several times faster.

The export also has a few title/metadata rows (report name, row count,
generation timestamp) before the real header row, so the header is detected
by content — a row containing both "RUC" and "NOMBRE" once normalized — not
assumed to be a fixed row number. The worksheet path itself is resolved from
`xl/workbook.xml`'s sheet relationships rather than assumed to be
`sheet1.xml`, so an export that ever gains a second/leading sheet doesn't
silently get parsed against the wrong one.

Because parsing 226k rows takes several seconds even with the fast path, the
full parsed table is cached in memory (see `_companias_cache`) rather than
re-fetched per call, guarded by `_fetch_lock` so concurrent callers don't
independently download+parse the same ~35 MB file. That cache holds the
entire registry as one row list plus precomputed search indexes, which is a
non-trivial amount of memory (roughly a few hundred MB) — acceptable since
it's built lazily on first use, not at server startup, but worth knowing if
this process runs somewhere memory-constrained.

The same host also publishes a second, much smaller export: the registry of
firms/individuals authorized to act as external auditors (~190 KB / 1,447
rows). Same title-rows-before-header quirk, same parsing approach, but a
different id column ("IDENTIFICACION" instead of "RUC") — see
`_fetch_auditores`/`search_auditores`/`get_auditor_info` below. Small enough
that no memory tradeoff worth documenting applies to it.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import zipfile
from typing import Any
from unicodedata import category, normalize
from xml.etree import ElementTree as ET

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.tls import should_retry_insecure
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_EXCEL_URL = (
    "https://mercadodevalores.supercias.gob.ec/reportes/excel/directorio_companias.xlsx"
)
_DOWNLOAD_TIMEOUT = 90.0
# The real file is ~35 MB; this is a safety ceiling, not the expected size.
_MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
_HEADER_SCAN_LIMIT = 20
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Refreshed daily upstream; a few hours balances staleness against the cost
# of re-downloading/re-parsing ~35 MB.
_companias_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
# Guards the cache-miss path so concurrent callers don't each independently
# download+parse the full export (a ~30-40s, ~35 MB operation).
_fetch_lock = asyncio.Lock()

# Lazily-built RUC -> row index, invalidated whenever the cached row list is
# replaced (compared by identity, not equality, so a cache refresh always
# rebuilds it). Only get_compania_by_ruc needs this; search_companias doesn't,
# so it isn't computed on every cache refresh regardless of which tool is used.
_ruc_index_state: tuple[list[tuple[str, ...]], dict[str, tuple[str, ...]]] | None = None
_expediente_index_state: (
    tuple[list[tuple[str, ...]], dict[str, tuple[str, ...]]] | None
) = None


def _strip(text: str) -> str:
    nfkd = normalize("NFKD", text or "")
    return "".join(c for c in nfkd if category(c) != "Mn").lower()


def _normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _strip(header)).strip("_")


def _col_index(ref: str) -> int:
    """Convert a cell reference like 'AC12' to a 0-based column index."""
    letters = "".join(c for c in ref if c.isalpha())
    idx = 0
    for c in letters:
        idx = idx * 26 + (ord(c.upper()) - ord("A") + 1)
    return idx - 1


def _first_worksheet_path(z: zipfile.ZipFile) -> str:
    """Resolve the first sheet listed in xl/workbook.xml via its relationship.

    Not assumed to be "xl/worksheets/sheet1.xml": that's true for the current
    export, but only because of how its generator happens to lay out the zip,
    not because OOXML guarantees it. Reading the actual sheet ->
    relationship -> target mapping means an export that gains a second or
    reordered sheet still resolves to the right one instead of silently
    parsing the wrong worksheet.
    """
    try:
        with z.open("xl/workbook.xml") as f:
            wb_root = ET.parse(f).getroot()
        sheet_elem = wb_root.find(f"{_NS}sheets/{_NS}sheet")
        if sheet_elem is None:
            raise ValueError("xl/workbook.xml no declara ninguna hoja")
        r_id = sheet_elem.get(f"{_R_NS}id")

        with z.open("xl/_rels/workbook.xml.rels") as f:
            rels_root = ET.parse(f).getroot()
        for rel in rels_root.findall(f"{_REL_NS}Relationship"):
            if rel.get("Id") == r_id:
                target = rel.get("Target") or ""
                # OPC relationship targets are either package-root-relative
                # ("/xl/worksheets/sheet1.xml", seen from openpyxl) or
                # relative to the referencing part's directory
                # ("worksheets/sheet1.xml", relative to "xl/" since this
                # relates from xl/workbook.xml — seen in the real Supercías
                # export).
                if target.startswith("/"):
                    return target.lstrip("/")
                return f"xl/{target}"
        raise ValueError(f"No se encontró la relación '{r_id}' de la primera hoja")
    except KeyError as exc:
        raise ValueError(
            "El export de Supercías no tiene la estructura OOXML esperada "
            "(falta xl/workbook.xml o xl/_rels/workbook.xml.rels)"
        ) from exc


def _read_shared_strings(z: zipfile.ZipFile) -> list[str]:
    # Present when strings are stored by index (the real Supercías export);
    # absent for writers that use inline strings instead (e.g. some openpyxl
    # configurations, including this project's own test fixtures).
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    shared: list[str] = []
    with z.open("xl/sharedStrings.xml") as f:
        for _, elem in ET.iterparse(f):
            if elem.tag == _NS + "si":
                texts = elem.findall(f".//{_NS}t")
                shared.append("".join(t.text or "" for t in texts))
                elem.clear()
    return shared


def _row_cells(elem: ET.Element, shared: list[str]) -> dict[int, str]:
    cells: dict[int, str] = {}
    for c in elem.findall(_NS + "c"):
        ref = c.get("r")
        if not ref:
            continue
        cell_type = c.get("t")
        if cell_type == "inlineStr":
            inline = c.find(_NS + "is")
            if inline is None:
                continue
            texts = inline.findall(f".//{_NS}t")
            cells[_col_index(ref)] = "".join(t.text or "" for t in texts)
            continue
        v = c.find(_NS + "v")
        if v is None or v.text is None:
            continue
        val = v.text
        if cell_type == "s":
            val = shared[int(val)]
        cells[_col_index(ref)] = val
    return cells


def _parse_xlsx(
    raw: bytes, header_markers: tuple[str, ...] = ("ruc", "nombre")
) -> tuple[tuple[str, ...], list[tuple[str, ...]]]:
    """Parse a Supercías Excel export into (fields, rows).

    `header_markers` are the normalized column names used to detect which
    scanned row is the real header — every Supercías export has a few
    title/metadata rows before it. Different reports use different id
    columns (the company directory has "RUC", the external-auditors report
    has "IDENTIFICACION" instead), so this isn't hardcoded to one report.
    """
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        shared = _read_shared_strings(z)
        sheet_path = _first_worksheet_path(z)
        fields: tuple[str, ...] | None = None
        rows: list[tuple[str, ...]] = []
        scanned = 0
        max_seen_col = -1
        header_label = "/".join(m.upper() for m in header_markers)
        with z.open(sheet_path) as f:
            for _, elem in ET.iterparse(f, events=("end",)):
                if elem.tag != _NS + "row":
                    continue
                cells = _row_cells(elem, shared)
                elem.clear()
                row_max = max(cells, default=-1)
                max_seen_col = max(max_seen_col, row_max)
                if fields is None:
                    scanned += 1
                    if scanned > _HEADER_SCAN_LIMIT:
                        raise ValueError(
                            f"No se encontró la fila de encabezado ({header_label}) "
                            "en el reporte de Supercías"
                        )
                    candidate = tuple(
                        _normalize_header(cells.get(i, "")) for i in range(row_max + 1)
                    )
                    if all(marker in candidate for marker in header_markers):
                        fields = candidate
                    continue
                width = len(fields)
                rows.append(tuple(cells.get(i, "") for i in range(width)))
        if fields is None:
            raise ValueError(
                f"No se encontró la fila de encabezado ({header_label}) en el "
                "reporte de Supercías"
            )
        if max_seen_col >= len(fields):
            # A data row has a cell past the last column the header row
            # produced — the header itself must be missing trailing
            # columns (most likely a blank header cell dropped entirely
            # from the row's XML rather than an empty string). Fail loudly
            # instead of silently truncating every row to fewer columns
            # than the file actually has.
            raise ValueError(
                f"El reporte de Supercías tiene datos en la columna "
                f"{max_seen_col + 1}, más allá de las {len(fields)} columnas "
                "detectadas en el encabezado; el encabezado parece estar "
                "incompleto"
            )
        return fields, rows


async def _download_once(url: str, verify: bool = True) -> bytes:
    async with (
        httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=_DOWNLOAD_TIMEOUT,
            verify=verify,
        ) as session,
        session.stream("GET", url) as resp,
    ):
        resp.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        async for chunk in resp.aiter_bytes(chunk_size=256 * 1024):
            chunks.append(chunk)
            total += len(chunk)
            if total > _MAX_DOWNLOAD_BYTES:
                raise ValueError(
                    f"El export de Supercías superó el límite de "
                    f"{_MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB; se abortó la descarga"
                )
    return b"".join(chunks)


async def _download_full(url: str) -> bytes:
    try:
        return await _download_once(url)
    except httpx.ConnectError as exc:
        if not should_retry_insecure(exc, url):
            raise
        logger.warning(
            "Fallo la verificación TLS para %s (¿certificado de Supercías con "
            "problemas?); reintentando sin verificación",
            url,
        )
        return await _download_once(url, verify=False)


async def _fetch_companias() -> tuple[
    tuple[str, ...], list[tuple[str, ...]], list[str], list[str], list[str]
]:
    """Return (fields, rows, normalized_names, normalized_provincias,
    normalized_situaciones), from cache or fresh."""
    cached = _companias_cache.get("companias")
    if cached is not None:
        return cached

    async with _fetch_lock:
        # Another coroutine may have populated the cache while this one was
        # waiting for the lock; re-check before downloading again.
        cached = _companias_cache.get("companias")
        if cached is not None:
            return cached

        logger.info("Descargando y parseando el directorio de Supercías (~35 MB)")
        try:
            raw = await _download_full(_EXCEL_URL)
            # _parse_xlsx is CPU-bound (streaming XML parse over ~35 MB) and
            # takes seconds; running it inline would block the event loop for
            # every other concurrent request on this server for that whole
            # window, not just this one.
            fields, rows = await asyncio.to_thread(_parse_xlsx, raw)
        except Exception:
            logger.exception("Fallo al descargar/parsear el directorio de Supercías")
            raise

        nombre_pos = fields.index("nombre")
        provincia_pos = fields.index("provincia")
        situacion_pos = fields.index("situacion_legal")
        normalized_names = [_strip(row[nombre_pos]) for row in rows]
        normalized_provincias = [_strip(row[provincia_pos]) for row in rows]
        normalized_situaciones = [_strip(row[situacion_pos]) for row in rows]

        bundle = (fields, rows, normalized_names, normalized_provincias, normalized_situaciones)
        _companias_cache.set("companias", bundle)
        logger.info("Directorio de Supercías cargado: %d compañías", len(rows))
        return bundle


def _ruc_index_for(
    fields: tuple[str, ...], rows: list[tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    """Build (and cache, by identity of `rows`) the RUC -> row lookup.

    Built lazily instead of alongside the main table in `_fetch_companias`
    because only get_compania_by_ruc needs it; search_companias doesn't, so
    a cache window with only search calls never pays for it.
    """
    global _ruc_index_state
    if _ruc_index_state is not None and _ruc_index_state[0] is rows:
        return _ruc_index_state[1]

    ruc_pos = fields.index("ruc")
    index: dict[str, tuple[str, ...]] = {}
    duplicates = 0
    for row in rows:
        ruc = row[ruc_pos]
        if not ruc:
            continue
        if ruc in index:
            duplicates += 1
        index[ruc] = row
    if duplicates:
        logger.warning(
            "Directorio de Supercías: %d RUC(s) duplicados en el export; "
            "se conserva la última fila vista de cada uno",
            duplicates,
        )
    _ruc_index_state = (rows, index)
    return index


def _expediente_index_for(
    fields: tuple[str, ...], rows: list[tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    """Build (and cache, by identity of `rows`) the expediente -> row lookup.

    Same lazy-by-identity pattern as `_ruc_index_for`; kept as a separate
    dict rather than folded into it since the two id spaces don't overlap
    (expediente is a small integer string, RUC is 13 digits) but callers
    look up by one or the other, not both.
    """
    global _expediente_index_state
    if _expediente_index_state is not None and _expediente_index_state[0] is rows:
        return _expediente_index_state[1]

    expediente_pos = fields.index("expediente")
    index: dict[str, tuple[str, ...]] = {}
    for row in rows:
        expediente = row[expediente_pos]
        if expediente:
            index[expediente] = row
    _expediente_index_state = (rows, index)
    return index


def _row_to_dict(fields: tuple[str, ...], row: tuple[str, ...]) -> dict[str, str]:
    return dict(zip(fields, row, strict=True))


async def search_companias(
    query: str = "",
    provincia: str = "",
    situacion_legal: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Search the Supercías company directory client-side.

    Args:
        query: Free text matched (accent-insensitive) against company name or RUC.
        provincia: Optional substring filter on province (accent-insensitive).
        situacion_legal: Optional substring filter on legal status.
        limit: Max results returned.
        offset: Pagination offset over the matched set.
    """
    fields, rows, normalized_names, normalized_provincias, normalized_situaciones = (
        await _fetch_companias()
    )
    ruc_pos = fields.index("ruc")

    q = _strip(query)
    prov = _strip(provincia)
    situ = _strip(situacion_legal)

    matched: list[int] = []
    for i, row in enumerate(rows):
        if q and q not in normalized_names[i] and q not in row[ruc_pos]:
            continue
        if prov and prov not in normalized_provincias[i]:
            continue
        if situ and situ not in normalized_situaciones[i]:
            continue
        matched.append(i)

    page = matched[offset : offset + limit]
    return {
        "total": len(matched),
        "offset": offset,
        "source": "Superintendencia de Compañías, Valores y Seguros — Directorio de Companias",
        "url_fuente": _EXCEL_URL,
        "companias": [_row_to_dict(fields, rows[i]) for i in page],
    }


async def get_compania_by_ruc(ruc: str) -> dict[str, str] | None:
    """Look up a single company by exact RUC match."""
    fields, rows, *_ = await _fetch_companias()
    ruc_index = _ruc_index_for(fields, rows)
    row = ruc_index.get((ruc or "").strip())
    if row is None:
        return None
    return _row_to_dict(fields, row)


async def get_compania_by_expediente(expediente: str) -> dict[str, str] | None:
    """Look up a single company by exact expediente match.

    search_companias's free-text query only matches name/RUC, not
    expediente, so it cannot be used as a substitute for this -- a caller
    that tried `search_companias(query=str(expediente))` would silently
    get no match for almost every real expediente.
    """
    fields, rows, *_ = await _fetch_companias()
    expediente_index = _expediente_index_for(fields, rows)
    row = expediente_index.get((expediente or "").strip())
    if row is None:
        return None
    return _row_to_dict(fields, row)


# Separate, much smaller export (~190 KB / 1,447 rows vs. ~35 MB / 226k) --
# the registry of firms/individuals authorized to act as external auditors
# in Ecuador. Same host, same title-rows-before-header quirk, but its id
# column is "IDENTIFICACION" rather than "RUC", so it needs its own header
# markers when calling the shared _parse_xlsx.
_AUDITORES_EXCEL_URL = (
    "https://mercadodevalores.supercias.gob.ec/reportes/excel/auditores_externos.xlsx"
)
_auditores_cache = TtlCache(ttl_seconds=21600.0, max_entries=1)
_auditores_fetch_lock = asyncio.Lock()

_identificacion_index_state: (
    tuple[list[tuple[str, ...]], dict[str, tuple[str, ...]]] | None
) = None


async def _fetch_auditores() -> tuple[
    tuple[str, ...], list[tuple[str, ...]], list[str], list[str]
]:
    """Return (fields, rows, normalized_names, normalized_provincias), from cache or fresh."""
    cached = _auditores_cache.get("auditores")
    if cached is not None:
        return cached

    async with _auditores_fetch_lock:
        cached = _auditores_cache.get("auditores")
        if cached is not None:
            return cached

        logger.info("Descargando y parseando el listado de auditores externos de Supercías")
        try:
            raw = await _download_full(_AUDITORES_EXCEL_URL)
            fields, rows = _parse_xlsx(raw, header_markers=("identificacion", "nombre"))
        except Exception:
            logger.exception("Fallo al descargar/parsear el listado de auditores externos")
            raise

        nombre_pos = fields.index("nombre")
        provincia_pos = fields.index("provincia")
        normalized_names = [_strip(row[nombre_pos]) for row in rows]
        normalized_provincias = [_strip(row[provincia_pos]) for row in rows]

        bundle = (fields, rows, normalized_names, normalized_provincias)
        _auditores_cache.set("auditores", bundle)
        logger.info("Listado de auditores externos cargado: %d registros", len(rows))
        return bundle


def _identificacion_index_for(
    fields: tuple[str, ...], rows: list[tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    """Build (and cache, by identity of `rows`) the identificación -> row lookup."""
    global _identificacion_index_state
    if _identificacion_index_state is not None and _identificacion_index_state[0] is rows:
        return _identificacion_index_state[1]

    id_pos = fields.index("identificacion")
    index: dict[str, tuple[str, ...]] = {}
    for row in rows:
        identificacion = row[id_pos]
        if identificacion:
            index[identificacion] = row
    _identificacion_index_state = (rows, index)
    return index


async def search_auditores(
    query: str = "",
    provincia: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Search the Supercías external-auditors registry client-side.

    Args:
        query: Free text matched (accent-insensitive) against auditor name
            or identificación (RUC/cédula).
        provincia: Optional substring filter on province (accent-insensitive).
        limit: Max results returned.
        offset: Pagination offset over the matched set.
    """
    fields, rows, normalized_names, normalized_provincias = await _fetch_auditores()
    id_pos = fields.index("identificacion")

    q = _strip(query)
    prov = _strip(provincia)

    matched: list[int] = []
    for i, row in enumerate(rows):
        if q and q not in normalized_names[i] and q not in row[id_pos]:
            continue
        if prov and prov not in normalized_provincias[i]:
            continue
        matched.append(i)

    page = matched[offset : offset + limit]
    return {
        "total": len(matched),
        "offset": offset,
        "source": (
            "Superintendencia de Compañías, Valores y Seguros — "
            "Listado de Auditores Externos"
        ),
        "url_fuente": _AUDITORES_EXCEL_URL,
        "auditores": [_row_to_dict(fields, rows[i]) for i in page],
    }


async def get_auditor_info(identificacion: str) -> dict[str, str] | None:
    """Look up a single external auditor by exact identificación (RUC/cédula) match."""
    fields, rows, *_ = await _fetch_auditores()
    id_index = _identificacion_index_for(fields, rows)
    row = id_index.get((identificacion or "").strip())
    if row is None:
        return None
    return _row_to_dict(fields, row)

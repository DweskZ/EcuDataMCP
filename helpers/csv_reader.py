import asyncio
import codecs
import csv
import difflib
import io
import json
import logging
import os
import re
import ssl
import struct
import tarfile
import weakref
import zipfile
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import unquote, urlsplit

import httpx

from helpers.cache import TtlCache
from helpers.geo_proxy import proxy_for
from helpers.logging import MAIN_LOGGER_NAME
from helpers.safe_download import UnsafeUrlError, safe_stream
from helpers.tls import (
    host_allows_insecure_tls,
    host_needs_legacy_ciphers,
    legacy_cipher_context,
    os_trust_context,
    should_retry_insecure,
    should_retry_with_os_trust,
)
from helpers.user_agent import USER_AGENT
from helpers.zip_blob import SpooledBlob

logger = logging.getLogger(MAIN_LOGGER_NAME)

MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024  # 20 MB
_TIMEOUT = 30.0
# Synchronous parsers (openpyxl, xlrd, pyxlsb, odfpy, pypdf) run in a worker
# thread with this bound, so a huge or pathological file never stalls every
# other request on the event loop.
PARSE_TIMEOUT_SECONDS = 60.0

T = TypeVar("T")


async def run_parser_off_loop(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking parser in a thread, failing with a clear message on timeout."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs), timeout=PARSE_TIMEOUT_SECONDS
        )
    except TimeoutError as e:
        raise ValueError(
            f"El archivo tardó más de {int(PARSE_TIMEOUT_SECONDS)} s en analizarse; "
            "es demasiado grande o está dañado para previsualizarlo aquí."
        ) from e


_GEOM_COLUMN_NAMES = {"geom", "geometry", "the_geom", "wkt", "wkt_geom", "shape"}
_WKT_PREFIXES = (
    "POINT",
    "LINESTRING",
    "POLYGON",
    "MULTIPOINT",
    "MULTILINESTRING",
    "MULTIPOLYGON",
    "GEOMETRYCOLLECTION",
)

# "7.760,2" (thousands dot, decimal comma) or plain "168,15". A lone comma
# followed by exactly 3 digits ("1,500", "23,000") is NOT matched: it is the
# US thousands format as often as a 3-decimal European value, and guessing
# wrong is a 1000x error, so such columns are left untouched.
_EU_DECIMAL_RE = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+,\d+|\d+,\d{1,2}|\d+,\d{4,})$")
_EU_AMBIGUOUS_RE = re.compile(r"^-?\d{1,3},\d{3}$")
# "1.000" / "12.500.000": a whole number with dot thousands. Only converted
# once the column has qualified as European through its sampled cells.
_EU_THOUSANDS_RE = re.compile(r"^-?\d{1,3}(?:\.\d{3})+$")


def _looks_like_wkt(value: str) -> bool:
    return value.strip().upper().startswith(_WKT_PREFIXES)


def strip_geometry_columns(
    headers: list[str], rows: list[list[str]]
) -> tuple[list[str], list[list[str]], list[str]]:
    """Drop columns that look like WKT/geometry data, by column name or content.

    A single polygon/multipolygon cell can be tens of KB of coordinates,
    which drowns out the rest of a preview. Returns (headers, rows, dropped_names).
    """
    if not headers:
        return headers, rows, []

    drop_idx: list[int] = []
    for i, name in enumerate(headers):
        if name.strip().lower() in _GEOM_COLUMN_NAMES:
            drop_idx.append(i)
            continue
        sample = [row[i] for row in rows[:5] if i < len(row) and row[i]]
        if sample and all(_looks_like_wkt(v) for v in sample):
            drop_idx.append(i)

    if not drop_idx:
        return headers, rows, []

    drop_set = set(drop_idx)
    dropped_names = [headers[i] for i in drop_idx]
    new_headers = [h for i, h in enumerate(headers) if i not in drop_set]
    new_rows = [
        [cell for i, cell in enumerate(row) if i not in drop_set] for row in rows
    ]
    return new_headers, new_rows, dropped_names


def _convert_eu_decimal(value: str) -> str:
    v = value.strip()
    sign = "-" if v.startswith("-") else ""
    v = v.lstrip("-").replace(".", "").replace(",", ".")
    return sign + v


def normalize_eu_decimal_columns(
    headers: list[str], rows: list[list[str]]
) -> tuple[list[list[str]], list[str]]:
    """Convert columns formatted as European decimals (7.760,2 -> 7760.2).

    Ecuadorian government CSVs commonly use dot-thousands/comma-decimal
    notation. Left as-is, those values sort and parse wrong downstream.
    A column only qualifies if every sampled value matches the pattern, so
    genuinely ambiguous columns are left untouched. Returns (rows, converted_names).
    """
    if not headers or not rows:
        return rows, []

    def all_cells(i: int) -> list[str]:
        return [row[i] for row in rows if i < len(row) and row[i]]

    idxs: list[int] = []
    for i in range(len(headers)):
        sample = [row[i] for row in rows[:5] if i < len(row) and row[i]]
        if (
            sample
            and all(_EU_DECIMAL_RE.match(v.strip()) for v in sample)
            and not any(_EU_AMBIGUOUS_RE.match(c.strip()) for c in all_cells(i))
        ):
            idxs.append(i)

    if not idxs:
        return rows, []

    idx_set = set(idxs)
    new_rows = [
        [
            _convert_eu_decimal(cell)
            if i in idx_set
            and cell
            and (_EU_DECIMAL_RE.match(cell.strip()) or _EU_THOUSANDS_RE.match(cell.strip()))
            else cell
            for i, cell in enumerate(row)
        ]
        for row in rows
    ]
    return new_rows, [headers[i] for i in idxs]


def _insecure_client(url: str) -> httpx.AsyncClient:
    """Cliente sin verificación TLS, limitado a hosts de la lista permitida.

    El reintento inseguro se decide sobre la URL original, pero safe_stream()
    sigue las redirecciones salto a salto; sin este hook un redirect a otro
    host heredaría verify=False. El hook corre en cada petición y rechaza
    cualquier host fuera de la lista.
    """

    async def _only_allowed_hosts(request: httpx.Request) -> None:
        if not host_allows_insecure_tls(str(request.url)):
            raise UnsafeUrlError(
                f"Redirección a '{request.url.host}' rechazada: no se permite "
                "TLS sin verificar fuera de los hosts permitidos"
            )

    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        verify=False,
        proxy=proxy_for(url),
        event_hooks={"request": [_only_allowed_hosts]},
    )


def _should_raise(resp: httpx.Response, raise_for_status: bool | frozenset[int]) -> bool:
    if isinstance(raise_for_status, bool):
        return raise_for_status
    return resp.status_code not in raise_for_status


async def _download(
    session: httpx.AsyncClient,
    url: str,
    *,
    raise_for_status: bool | frozenset[int] = True,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    on_chunk: Callable[[bytes], None] | None = None,
) -> tuple[bytes, bool]:
    truncated = False
    # `url` comes from CKAN resource metadata -- external, not first-party --
    # so every hop (including redirects) must be checked against the SSRF
    # guard rather than trusting httpx's own follow_redirects.
    async with safe_stream(session, url, timeout=_TIMEOUT) as resp:
        if _should_raise(resp, raise_for_status):
            resp.raise_for_status()

        # Content-Length is advisory only: a server can overstate it (and a
        # fully received file must not be refused for it) or send garbage;
        # the byte counter below is what decides `truncated`.
        chunks: list[bytes] = []
        total = 0
        async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
            if on_chunk is None:
                chunks.append(chunk)
            else:
                on_chunk(chunk)
            total += len(chunk)
            if total > max_bytes:
                truncated = True
                break

    return b"".join(chunks), truncated


async def download_bytes(
    url: str,
    session: httpx.AsyncClient | None = None,
    *,
    raise_for_status: bool | frozenset[int] = True,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    on_chunk: Callable[[bytes], None] | None = None,
) -> tuple[bytes, bool]:
    """Download up to `max_bytes` (default MAX_DOWNLOAD_BYTES) with TLS
    fallback for portal hosts.

    raise_for_status also accepts a frozenset of status codes to tolerate
    while still raising on any other non-2xx -- a narrow escape hatch for a
    confirmed host quirk (a WordPress/Elementor bug on censoecuador.gob.ec's
    /data-y-resultados/ page serves a real, substantial page under an HTTP
    404: callers pass frozenset({404})). Plain False tolerates every status;
    default stays True so every other caller keeps failing loudly on a
    genuine error response.

    max_bytes is an explicit override for callers whose format offers no
    partial-download benefit -- a ZIP-container spreadsheet (.xlsx/.xlsb/
    .ods) needs its central directory, which lives at the end of the file,
    so a truncated download at the default cap fails outright rather than
    degrading gracefully the way a truncated CSV still yields some rows.
    Raising the cap for those formats specifically (see preview_xlsx/
    preview_xlsb/preview_ods) trades a bounded amount of extra worst-case
    bandwidth for turning a guaranteed failure into a successful preview.

    on_chunk hands every 64 KB chunk to a callback (a file or a SpooledBlob)
    instead of keeping it, and the returned bytes are then empty, so a file far
    past memory can be downloaded. A TLS retry only happens when the handshake
    fails, before any chunk, so the callback never sees a partial first attempt.
    """
    own = session is None
    if own:
        # follow_redirects is deliberately not set here: safe_stream() always
        # makes its own per-request follow_redirects=False and handles
        # redirects itself (validating each hop), so a client-level default
        # would be misleading rather than wrong.
        # Hosts with old TLS configs need SECLEVEL=1 to complete the
        # handshake at all; the certificate is still verified.
        verify: ssl.SSLContext | bool = (
            legacy_cipher_context() if host_needs_legacy_ciphers(url) else True
        )
        session = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, proxy=proxy_for(url), verify=verify
        )
    assert session is not None
    try:
        logger.debug("Downloading from %s (max %d bytes)", url, max_bytes)
        try:
            return await _download(
                session,
                url,
                raise_for_status=raise_for_status,
                max_bytes=max_bytes,
                on_chunk=on_chunk,
            )
        except httpx.ConnectError as exc:
            if should_retry_with_os_trust(exc, url):
                logger.warning(
                    "TLS verification failed for %s: server didn't send its "
                    "intermediate CA; retrying with it bundled locally "
                    "(still fully verified)",
                    url,
                )
                async with httpx.AsyncClient(
                    headers={"User-Agent": USER_AGENT},
                    verify=os_trust_context(),
                    proxy=proxy_for(url),
                ) as os_trust_session:
                    return await _download(
                        os_trust_session,
                        url,
                        raise_for_status=raise_for_status,
                        max_bytes=max_bytes,
                        on_chunk=on_chunk,
                    )
            if not should_retry_insecure(exc, url):
                raise
            logger.warning(
                "TLS verification failed for %s (portal cert expired); "
                "retrying without verification",
                url,
            )
            async with _insecure_client(url) as insecure_session:
                return await _download(
                    insecure_session,
                    url,
                    raise_for_status=raise_for_status,
                    max_bytes=max_bytes,
                    on_chunk=on_chunk,
                )
    finally:
        if own:
            await session.aclose()


async def post_json_bytes(
    url: str,
    body: dict[str, Any],
    *,
    timeout: float = 60.0,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> tuple[bytes, bool]:
    """POST a JSON body to a fixed first-party API and read the response up
    to `max_bytes`, the same cap download_bytes applies to GETs. Returns
    (content, truncated). Not for URLs taken from external metadata: there
    is no SSRF hop validation here because redirects are not followed."""
    chunks: list[bytes] = []
    total = 0
    async with (
        httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=False
        ) as client,
        client.stream("POST", url, json=body) as resp,
    ):
        resp.raise_for_status()
        async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                return b"".join(chunks), True
    return b"".join(chunks), False


async def sniff_content_type(
    url: str, session: httpx.AsyncClient | None = None
) -> str | None:
    """Best-effort Content-Type sniff for a resource with no recognizable
    URL extension and no useful declared CKAN format.

    Opens the same safe_stream() a real download would use but returns as
    soon as headers arrive, without reading the body -- costs a connection,
    not a download. Best-effort: any failure just means no hint, callers
    fall back to their existing "unsupported format" handling.
    """
    own = session is None
    if own:
        session = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, proxy=proxy_for(url)
        )
    assert session is not None
    try:
        async with safe_stream(session, url, timeout=_TIMEOUT) as resp:
            return resp.headers.get("content-type")
    except (httpx.HTTPError, UnsafeUrlError):
        return None
    finally:
        if own:
            await session.aclose()


def _decode_text(raw: bytes, truncated: bool = False) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        # A download cut at the size cap can end inside a multibyte UTF-8
        # character; final=False tolerates that instead of falling through
        # to latin-1 and garbling every accent in the file.
        return codecs.getincrementaldecoder("utf-8")().decode(raw, final=not truncated)
    except UnicodeDecodeError:
        pass
    # cp1252 before latin-1: latin-1 never fails, and would leave Windows
    # smart quotes and the euro sign as C1 control characters.
    for encoding in ("cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


_MAX_CONTAINER_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def _check_zip_container_size(raw: bytes, label: str) -> None:
    """Reject a .xlsx/.ods whose parts expand far beyond the download cap.

    The 20 MB limit applies to the compressed bytes; openpyxl and odfpy parse
    shared strings / content.xml fully into memory, so a hostile file could
    expand to gigabytes.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            total = sum(info.file_size for info in zf.infolist())
    except zipfile.BadZipFile:
        return  # the real parser reports the corrupt container
    if total > _MAX_CONTAINER_UNCOMPRESSED_BYTES:
        raise ValueError(
            f"El archivo {label} se expande a más de "
            f"{_MAX_CONTAINER_UNCOMPRESSED_BYTES // (1024 * 1024)} MB al "
            "descomprimirse; el preview lo rechaza. Descarga el enlace directo del "
            "recurso."
        )


def _sniff_delimiter(sample: str) -> str:
    """Guess the field delimiter from a text sample.

    Prefers csv.Sniffer (which weighs consistency across rows, not just raw
    counts) since a naive whole-sample character count is skewed by
    comma-heavy free-text fields (e.g. Spanish prose descriptions) that can
    outnumber a real ';'/tab delimiter — confirmed live against Contraloría's
    audit-report CSVs, where "," (30 occurrences, mostly inside description
    text) narrowly beat ";" (29, the actual delimiter) in a 2000-char
    sample. Falls back to counting occurrences in just the header line
    (first row only, not the whole sample) when Sniffer can't decide.
    """
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        pass
    first_line = sample.split("\n", 1)[0]
    delimiter = ","
    for candidate in (";", "\t", "|"):
        if first_line.count(candidate) > first_line.count(delimiter):
            delimiter = candidate
    return delimiter


def _parse_csv_bytes(raw: bytes, max_rows: int, truncated: bool = False) -> dict[str, Any]:
    text = _decode_text(raw, truncated)

    sample = text[:2000]
    delimiter = _sniff_delimiter(sample)

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows_read: list[list[str]] = []
    try:
        for row in reader:
            rows_read.append(row)
            if len(rows_read) > max_rows + 1:
                truncated = True
                break
    except csv.Error as e:
        # Found for real: a .zip's picked "first tabular-looking member" can
        # still turn out to be a binary file misidentified by its extension,
        # or a genuinely malformed export. Keep whatever rows parsed cleanly
        # before the bad one rather than losing the whole preview to it.
        truncated = True
        if not rows_read:
            raise ValueError(
                "El contenido no se pudo parsear como CSV (formato inválido "
                f"o no es realmente texto tabular): {e}"
            ) from e

    if not rows_read:
        return {"headers": [], "rows": [], "total_rows_in_preview": 0, "truncated": truncated}

    headers = rows_read[0]
    data_rows = rows_read[1 : max_rows + 1]

    headers, data_rows, dropped_geom = strip_geometry_columns(headers, data_rows)
    data_rows, converted_decimals = normalize_eu_decimal_columns(headers, data_rows)

    result: dict[str, Any] = {
        "headers": headers,
        "rows": data_rows,
        "total_rows_in_preview": len(data_rows),
        "truncated": truncated,
    }
    if dropped_geom:
        result["dropped_columns"] = dropped_geom
    if converted_decimals:
        result["converted_decimal_columns"] = converted_decimals
    return result


async def preview_csv(
    url: str, max_rows: int = 20, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """
    Download a CSV file and return the first N rows parsed.

    Returns:
        dict with 'headers', 'rows', 'total_rows_in_preview', 'truncated'
    """
    raw, truncated = await download_bytes(url, session=session)
    result = _parse_csv_bytes(raw, max_rows, truncated=truncated)
    result["format"] = "csv"
    return result


async def preview_json(
    url: str, max_rows: int = 20, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Preview JSON / GeoJSON as a tabular sample when possible."""
    raw, truncated = await download_bytes(url, session=session)
    if truncated:
        raise ValueError(
            "El archivo JSON supera el límite de 5 MB de este preview, así que "
            "se descargó incompleto y no se puede interpretar. Usa "
            "el enlace directo del recurso para bajarlo completo."
        )
    text = _decode_text(raw, truncated)
    data = json.loads(text)

    if isinstance(data, dict) and "features" in data and isinstance(data["features"], list):
        features = data["features"]
        rows: list[list[str]] = []
        headers = ["id", "geometry_type", "properties"]
        for feat in features[:max_rows]:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            rows.append(
                [
                    str(feat.get("id", "")),
                    str(geom.get("type", "")),
                    json.dumps(props, ensure_ascii=False)[:200],
                ]
            )
        return {
            "headers": headers,
            "rows": rows,
            "total_rows_in_preview": len(rows),
            "truncated": truncated or len(features) > max_rows,
            "format": "geojson",
            "total_records": len(features),
        }

    if isinstance(data, list):
        if not data:
            return {
                "headers": [],
                "rows": [],
                "total_rows_in_preview": 0,
                "truncated": truncated,
                "format": "json",
            }
        if all(isinstance(item, dict) for item in data[:max_rows]):
            keys: list[str] = []
            for item in data[:max_rows]:
                for key in item:
                    if key not in keys:
                        keys.append(key)
            rows = [
                [str(item.get(k, ""))[:120] for k in keys] for item in data[:max_rows]
            ]
            keys, rows, dropped_geom = strip_geometry_columns(keys, rows)
            result: dict[str, Any] = {
                "headers": keys,
                "rows": rows,
                "total_rows_in_preview": len(rows),
                "truncated": truncated or len(data) > max_rows,
                "format": "json",
                "total_records": len(data),
            }
            if dropped_geom:
                result["dropped_columns"] = dropped_geom
            return result
        preview_items = data[:max_rows]
        return {
            "headers": ["value"],
            "rows": [[json.dumps(item, ensure_ascii=False)[:200]] for item in preview_items],
            "total_rows_in_preview": len(preview_items),
            "truncated": truncated or len(data) > max_rows,
            "format": "json",
            "total_records": len(data),
        }

    if isinstance(data, dict):
        headers = ["key", "value"]
        items = list(data.items())
        rows = [[str(k), str(v)[:200]] for k, v in items[:max_rows]]
        return {
            "headers": headers,
            "rows": rows,
            "total_rows_in_preview": len(rows),
            "truncated": truncated or len(items) > max_rows,
            "format": "json",
            "total_records": len(items),
        }

    return {
        "headers": ["value"],
        "rows": [[str(data)[:500]]],
        "total_rows_in_preview": 1,
        "truncated": truncated,
        "format": "json",
    }


def _cell_text(value: Any) -> str:
    """Text of a cell from a format that stores every number as a double.

    .xls and .xlsb keep 2024 as 2024.0, which would print as "2024.0" where
    the same sheet saved as .xlsx prints "2024": whole numbers drop the ".0".
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return str(value)


def _select_sheet(names: list[str], sheet: str) -> int:
    """Index of the requested sheet: "" -> 0, else a name, else a 1-based number.

    A name wins over a number, so a workbook whose sheets are called "2023" and
    "2024" (common in statistical publications) is read by those names, not by
    position. Names match exactly first, then case-insensitively and ignoring
    surrounding spaces; only a value that names no sheet and is a number picks
    by position. A miss raises ValueError listing the workbook's sheets.
    """
    wanted = (sheet or "").strip()
    if not wanted:
        return 0
    if wanted in names:
        return names.index(wanted)
    folded = [n.strip().casefold() for n in names]
    if wanted.casefold() in folded:
        return folded.index(wanted.casefold())
    if wanted.isdigit() and 1 <= int(wanted) <= len(names):
        return int(wanted) - 1
    listed = "; ".join(f"{i + 1}. {n}" for i, n in enumerate(names))
    raise ValueError(
        f"No hay una hoja '{sheet}' en el libro. Hojas disponibles: {listed}."
    )


def _parse_xlsx_bytes(
    raw: bytes, max_rows: int, truncated: bool, sheet: str = ""
) -> dict[str, Any]:
    from openpyxl import load_workbook

    _check_zip_container_size(raw, ".xlsx")
    wb = load_workbook(filename=io.BytesIO(raw), read_only=True, data_only=True)
    try:
        names = list(wb.sheetnames)
        ws = wb[names[_select_sheet(names, sheet)]] if sheet.strip() else wb.active
        if ws is None:
            return {
                "headers": [],
                "rows": [],
                "total_rows_in_preview": 0,
                "truncated": truncated,
                "format": "xlsx",
            }
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return {
                "headers": [],
                "rows": [],
                "total_rows_in_preview": 0,
                "truncated": truncated,
                "format": "xlsx",
            }
        headers = [str(c) if c is not None else "" for c in header_row]
        data_rows: list[list[str]] = []
        for i, row in enumerate(rows_iter):
            if i >= max_rows:
                truncated = True
                break
            data_rows.append([str(c) if c is not None else "" for c in row])
        return {
            "headers": headers,
            "rows": data_rows,
            "total_rows_in_preview": len(data_rows),
            "truncated": truncated,
            "format": "xlsx",
            "sheet": ws.title,
            "sheets": names,
        }
    finally:
        wb.close()


def _parse_xls_bytes(
    raw: bytes, max_rows: int, truncated: bool, sheet: str = ""
) -> dict[str, Any]:
    import xlrd

    wb = xlrd.open_workbook(file_contents=raw)
    names = list(wb.sheet_names())
    ws = wb.sheet_by_index(_select_sheet(names, sheet))

    if ws.nrows == 0:
        return {
            "headers": [],
            "rows": [],
            "total_rows_in_preview": 0,
            "truncated": truncated,
            "format": "xls",
        }

    headers = [_cell_text(v) for v in ws.row_values(0)]
    data_rows: list[list[str]] = []
    for i in range(1, ws.nrows):
        if len(data_rows) >= max_rows:
            truncated = True
            break
        data_rows.append([_cell_text(v) for v in ws.row_values(i)])

    return {
        "headers": headers,
        "rows": data_rows,
        "total_rows_in_preview": len(data_rows),
        "truncated": truncated,
        "format": "xls",
        "sheet": ws.name,
        "sheets": names,
    }


def _parse_xlsb_bytes(
    raw: bytes, max_rows: int, truncated: bool, sheet: str = ""
) -> dict[str, Any]:
    from pyxlsb import open_workbook

    _check_zip_container_size(raw, ".xlsb")
    wb = open_workbook(io.BytesIO(raw))
    try:
        if not wb.sheets:
            return {
                "headers": [],
                "rows": [],
                "total_rows_in_preview": 0,
                "truncated": truncated,
                "format": "xlsb",
            }
        names = list(wb.sheets)
        index = _select_sheet(names, sheet)
        ws = wb.get_sheet(index + 1)
        try:
            rows_iter = ws.rows()

            try:
                header_row = next(rows_iter)
            except StopIteration:
                return {
                    "headers": [],
                    "rows": [],
                    "total_rows_in_preview": 0,
                    "truncated": truncated,
                    "format": "xlsb",
                }
            headers = [_cell_text(c.v) for c in header_row]
            data_rows: list[list[str]] = []
            for i, row in enumerate(rows_iter):
                if i >= max_rows:
                    truncated = True
                    break
                data_rows.append([_cell_text(c.v) for c in row])
            return {
                "headers": headers,
                "rows": data_rows,
                "total_rows_in_preview": len(data_rows),
                "truncated": truncated,
                "format": "xlsb",
                "sheet": names[index],
                "sheets": names,
            }
        finally:
            ws.close()
    finally:
        wb.close()


def _parse_ods_bytes(
    raw: bytes, max_rows: int, truncated: bool, sheet: str = ""
) -> dict[str, Any]:
    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow
    from odf.teletype import extractText

    _check_zip_container_size(raw, ".ods")
    doc = load(io.BytesIO(raw))
    tables = doc.spreadsheet.getElementsByType(Table)
    empty = {
        "headers": [],
        "rows": [],
        "total_rows_in_preview": 0,
        "truncated": truncated,
        "format": "ods",
    }
    if not tables:
        return empty
    names = [str(t.getAttribute("name")) for t in tables]
    table = tables[_select_sheet(names, sheet)]

    def row_values(row: TableRow) -> list[str]:
        values: list[str] = []
        for cell in row.getElementsByType(TableCell):
            # ODS pads trailing empty columns with huge repeat counts (e.g.
            # 1024) to fill the sheet's fixed grid -- cap it, real header/data
            # rows never need more than a handful of repeated cells.
            repeat = min(int(cell.getAttribute("numbercolumnsrepeated") or 1), 50)
            values.extend([extractText(cell).strip()] * repeat)
        while values and values[-1] == "":
            values.pop()
        return values

    all_rows: list[list[str]] = []
    for row in table.getElementsByType(TableRow):
        values = row_values(row)
        if not values:
            continue
        repeat = min(int(row.getAttribute("numberrowsrepeated") or 1), max_rows + 2)
        for _ in range(repeat):
            all_rows.append(values)
            if len(all_rows) > max_rows + 1:
                break
        if len(all_rows) > max_rows + 1:
            break

    if not all_rows:
        return empty

    headers = all_rows[0]
    data_rows = all_rows[1 : max_rows + 1]
    if len(all_rows) - 1 > max_rows:
        truncated = True

    return {
        "headers": headers,
        "rows": data_rows,
        "total_rows_in_preview": len(data_rows),
        "truncated": truncated,
        "format": "ods",
        "sheet": table.getAttribute("name"),
        "sheets": names,
    }


async def preview_xlsx(
    url: str, max_rows: int = 20, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Preview the first sheet of an Excel workbook.

    .xlsx is a ZIP container whose central directory lives at the end of
    the file, so a download truncated at the default cap can't open at all
    (not a degraded-but-useful partial read the way a truncated CSV is) --
    see download_bytes' max_bytes docstring. Worth the larger cap since the
    alternative is a guaranteed failure, not a safety margin.
    """
    raw, truncated = await download_bytes(
        url, session=session, max_bytes=_MAX_DECOMPRESSED_BYTES
    )
    if truncated:
        raise ValueError(
            "El archivo .xlsx supera el límite de 20 MB de este preview, así "
            "que se descargó incompleto y no se puede abrir (el índice del "
            "contenedor ZIP interno vive al final del archivo). Usa "
            "el enlace directo del recurso para bajarlo completo."
        )

    return await run_parser_off_loop(_parse_xlsx_bytes, raw, max_rows, truncated)


async def preview_xls(
    url: str, max_rows: int = 20, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Preview the first sheet of a legacy Excel (.xls) workbook."""
    raw, truncated = await download_bytes(
        url, session=session, max_bytes=_MAX_DECOMPRESSED_BYTES
    )
    if truncated:
        raise ValueError(
            "El archivo .xls supera el límite de 20 MB de este preview, así "
            "que se descargó incompleto y no se puede abrir. Usa "
            "el enlace directo del recurso para bajarlo completo."
        )
    return await run_parser_off_loop(_parse_xls_bytes, raw, max_rows, truncated)


async def preview_xlsb(
    url: str, max_rows: int = 20, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Preview the first sheet of an Excel Binary Workbook (.xlsb)."""
    raw, truncated = await download_bytes(
        url, session=session, max_bytes=_MAX_DECOMPRESSED_BYTES
    )
    if truncated:
        # .xlsb is a ZIP container (BIFF12 records instead of XLSX's XML),
        # so it fails the exact same way a truncated .zip does: the central
        # directory lives at the end of the file, a download cut off before
        # the end is missing it, and zipfile can't open it at all -- same
        # reasoning as preview_xlsx/preview_ods, so this uses the same
        # raised _MAX_DECOMPRESSED_BYTES cap (20 MB) rather than the default
        # MAX_DOWNLOAD_BYTES (5 MB). Confirmed live against a real 9.3 MB
        # resource (Registro Civil's "Defunciones Generales", now well
        # inside the 20 MB cap) that a truncated read fails outright with
        # "File is not a zip file", not a partial/degraded one -- skip the
        # doomed parse attempt and say what actually happened, same as
        # preview_zip.
        raise ValueError(
            "El archivo .xlsb supera el límite de 20 MB de este preview, así "
            "que se descargó incompleto y no se puede abrir (el índice del "
            "contenedor ZIP interno vive al final del archivo). Usa "
            "el enlace directo del recurso para bajarlo completo."
        )

    return await run_parser_off_loop(_parse_xlsb_bytes, raw, max_rows, truncated)


async def preview_ods(
    url: str, max_rows: int = 20, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Preview the first sheet of an OpenDocument Spreadsheet (.ods).

    .ods is a ZIP container like .xlsx/.xlsb (see download_bytes' max_bytes
    docstring) -- same higher cap, same reasoning: a truncated download
    can't open at all, so there's no safety benefit to stopping early at
    the default cap, only a guaranteed failure.
    """

    raw, truncated = await download_bytes(
        url, session=session, max_bytes=_MAX_DECOMPRESSED_BYTES
    )
    if truncated:
        raise ValueError(
            "El archivo .ods supera el límite de 20 MB de este preview, así "
            "que se descargó incompleto y no se puede abrir (el índice del "
            "contenedor ZIP interno vive al final del archivo). Usa "
            "el enlace directo del recurso para bajarlo completo."
        )

    return await run_parser_off_loop(_parse_ods_bytes, raw, max_rows, truncated)


def _gunzip_capped(
    raw: bytes, cap: int = _MAX_DECOMPRESSED_BYTES
) -> tuple[bytes, bool]:
    """Decompress gzip bytes, stopping once `cap` output bytes are produced."""
    return _inflate_capped(raw, 16 + zlib.MAX_WBITS, cap)


def _inflate_capped(raw: bytes, wbits: int, cap: int) -> tuple[bytes, bool]:
    """Decompress zlib-family bytes, stopping once `cap` output bytes are produced.

    `wbits` picks the container: 16 + MAX_WBITS for gzip (.tar.gz), -MAX_WBITS
    for the raw deflate stream inside a .zip member. Returns (output,
    truncated).

    Bounds memory use against a decompression bomb: a small, highly
    compressible input (already capped at MAX_DOWNLOAD_BYTES on the wire)
    could otherwise expand to gigabytes once decompressed. Passing
    max_length to decompress() is essential here -- a single 64 KB
    compressed chunk can still expand far past `cap` in one call, so the
    cap must be enforced *within* a chunk, not just checked between chunks.
    """
    decompressor = zlib.decompressobj(wbits)
    out = bytearray()
    chunk_size = 64 * 1024
    pos = 0
    pending = b""
    while True:
        if not pending:
            if pos >= len(raw):
                break
            pending = raw[pos : pos + chunk_size]
            pos += chunk_size
        budget = cap - len(out)
        if budget <= 0:
            return bytes(out[:cap]), True
        piece = decompressor.decompress(pending, budget)
        out += piece
        new_pending = decompressor.unconsumed_tail
        if not piece and new_pending == pending:
            # No forward progress possible (truncated/malformed stream) --
            # stop instead of looping forever on the same unconsumed bytes.
            break
        pending = new_pending
    budget = cap - len(out)
    if budget > 0:
        out += decompressor.flush(budget)
    return bytes(out[:cap]), len(out) > cap


def _pick_member(names: list[str]) -> str | None:
    """Pick the best-priority member name: .csv > .tsv > .txt, or None if no
    member looks tabular.

    Prevents a bundled readme.txt from winning over the actual data file
    just because it comes first in the archive. Deliberately does NOT fall
    back to "just take the first file" -- confirmed against a real GIS
    raster .zip on the live portal (.lyr/.tif/.tif.aux.xml, no CSV at all)
    that a naive first-file fallback force-feeds a binary file into the CSV
    parser, which fails with a confusing raw csv.Error instead of a message
    that explains there's simply no tabular content in the archive.
    """
    # __MACOSX/._data.csv resource forks end in .csv but are binary.
    names = [
        n
        for n in names
        if not n.startswith("__MACOSX/") and not n.rsplit("/", 1)[-1].startswith("._")
    ]
    for ext in (".csv", ".tsv", ".txt"):
        match = next((n for n in names if n.lower().endswith(ext)), None)
        if match is not None:
            return match
    return None


async def preview_targz(
    url: str, max_rows: int = 20, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Preview the first CSV/TSV-like member inside a .tar.gz archive."""
    raw, truncated = await download_bytes(url, session=session)
    decompressed, capped = _gunzip_capped(raw)
    truncated = truncated or capped

    try:
        with tarfile.open(fileobj=io.BytesIO(decompressed), mode="r:") as tar:
            members = {m.name: m for m in tar.getmembers() if m.isfile()}
            if not members:
                return {
                    "headers": [],
                    "rows": [],
                    "total_rows_in_preview": 0,
                    "truncated": truncated,
                    "format": "tar_gz",
                }
            member_name = _pick_member(list(members))
            if member_name is None:
                sample = ", ".join(list(members)[:10])
                raise ValueError(
                    "Este .tar.gz no contiene ningún archivo .csv/.tsv/.txt "
                    f"identificable (archivos internos: {sample}). Puede que "
                    "no sea un dataset tabular. Descarga el enlace directo del "
                    "recurso (un .tar.gz no se puede leer por partes)."
                )
            extracted = tar.extractfile(members[member_name])
            inner_raw = extracted.read(MAX_DOWNLOAD_BYTES + 1) if extracted else b""
    except (tarfile.TarError, zlib.error) as e:
        if truncated:
            # Confirmed against a real 17MB .zip on the live portal (same
            # failure mode applies here): a real archive larger than the 5MB
            # download cap gets cut off mid-stream, which reads as corrupt to
            # tarfile. We already know why, so say that instead of guessing.
            raise ValueError(
                "El archivo .tar.gz descomprimido supera el límite de 5 MB de "
                "este preview y se cortó a la mitad. Descarga el enlace "
                "directo del recurso (un .tar.gz no se puede leer por partes)."
            ) from e
        raise ValueError(
            "El archivo .tar.gz no se pudo leer: está corrupto"
        ) from e

    truncated = truncated or len(inner_raw) > MAX_DOWNLOAD_BYTES
    inner_raw = inner_raw[:MAX_DOWNLOAD_BYTES]

    result = _parse_csv_bytes(inner_raw, max_rows, truncated=truncated)
    result["format"] = "tar_gz"
    result["member_name"] = member_name
    return result


async def preview_zip(
    url: str, max_rows: int = 20, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Preview the first CSV/TSV-like member inside a .zip archive.

    Unlike .tar.gz, a .zip's central directory lists members without
    decompressing anything, so there is no need for a capped-decompression
    pass up front — bounding the single chosen member's `.read()` call is
    enough to keep a decompression bomb from blowing up memory.
    """
    raw, truncated = await download_bytes(url, session=session)
    if truncated:
        # A .zip's central directory lives at the end of the file, so a
        # download cut off at MAX_DOWNLOAD_BYTES is missing it entirely --
        # zipfile can't open it at all, not even partially. Confirmed
        # against a real 17MB resource on the live portal: parsing wasn't
        # just degraded, it failed outright with "File is not a zip file".
        # Skip the doomed parse attempt and say what actually happened.
        raise ValueError(
            "El archivo .zip supera el límite de 5 MB de este preview, así "
            "que se descargó incompleto y no se puede abrir (el índice del "
            ".zip vive al final del archivo). Para leer un archivo de su interior "
            "sin bajarlo entero, pasa la URL del recurso a list_zip_contents y "
            "luego a read_zip_member (sirve cuando el servidor admite HTTP Range y, "
            "si no, hasta "
            f"{_no_range_zip_limit() // (1024 * 1024)} MB); o descarga el enlace "
            "directo."
        )

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            if not names:
                return {
                    "headers": [],
                    "rows": [],
                    "total_rows_in_preview": 0,
                    "truncated": truncated,
                    "format": "zip",
                }
            member_name = _pick_member(names)
            if member_name is None:
                sample = ", ".join(names[:10])
                raise ValueError(
                    "Este .zip no contiene ningún archivo .csv/.tsv/.txt "
                    f"identificable (archivos internos: {sample}). Puede que "
                    "no sea un dataset tabular (ej. un paquete GIS/raster). "
                    "Descarga el enlace directo del recurso, o lee un archivo "
                    "concreto con list_zip_contents y read_zip_member."
                )
            with zf.open(member_name) as f:
                inner_raw = f.read(MAX_DOWNLOAD_BYTES + 1)
    except zipfile.BadZipFile as e:
        raise ValueError(
            "El archivo .zip no se pudo leer: está corrupto"
        ) from e

    truncated = truncated or len(inner_raw) > MAX_DOWNLOAD_BYTES
    inner_raw = inner_raw[:MAX_DOWNLOAD_BYTES]

    result = _parse_csv_bytes(inner_raw, max_rows, truncated=truncated)
    result["format"] = "zip"
    result["member_name"] = member_name
    return result


# A .zip's central directory lives at the end of the file and lists every
# member's name/size without decompressing anything, so it can be listed via
# HTTP Range requests for archives far larger than MAX_DOWNLOAD_BYTES (e.g.
# INEC/censo multi-hundred-MB microdata ZIPs). The central directory also
# gives each member's local header offset, so read_zip_member (below) can
# Range-fetch one member's bytes without the rest of the archive.
_EOCD_SIGNATURE = b"PK\x05\x06"
_CD_HEADER_SIGNATURE = b"PK\x01\x02"
_EOCD_TAIL_BYTES = 65557 + 22  # max comment (65535) + EOCD record, plus slack
_MAX_CENTRAL_DIR_BYTES = 20 * 1024 * 1024  # same bound as _gunzip_capped's cap

_CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)")

# A host that ignores Range (the SRI's, for one, answers 200 with the whole
# file) cannot be read piece by piece. The .zip is downloaded whole, kept in
# memory up to _NO_RANGE_ZIP_RAM_BYTES and in a temporary file beyond that, and
# read through the same parsing as the Range path. _MAX_NO_RANGE_ZIP_BYTES is
# the largest download accepted: the SRI's province RUC zips are 2 to 156 MB.
_NO_RANGE_ZIP_RAM_BYTES = 20 * 1024 * 1024
_MAX_NO_RANGE_ZIP_BYTES = 400 * 1024 * 1024
_NO_RANGE_ZIP_ENV = "ECUADOR_MCP_NO_RANGE_ZIP_MB"
_NO_RANGE_ZIP_MAX_MB = 1024
# The SRI's host gave 0.16 to 0.5 MB/s from a home connection on 2026-11-27, so the
# 156 MB Pichincha zip needs 5 to 16 minutes there; a stalled read still fails at
# _TIMEOUT, and this only bounds a transfer that keeps trickling in.
_NO_RANGE_ZIP_DEADLINE_SECONDS = 600.0
# So that list_zip_contents followed by read_zip_member downloads it once.
_BLOB_CACHE_SECONDS = 300.0
_blob_cache = TtlCache(ttl_seconds=_BLOB_CACHE_SECONDS, max_entries=2, stale_seconds=0.0)
# One download per URL at a time: two calls for the same 150 MB zip share it.
_zip_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


class _RangeUnsupported(ValueError):
    """The host did not honor an HTTP Range request (no 206, or the wrong range)."""


async def _fetch_range(
    url: str,
    range_header: str,
    cap: int,
    session: httpx.AsyncClient | None = None,
) -> tuple[bytes, httpx.Headers, int]:
    """GET a byte range, capped at `cap` bytes, returning (body, headers, status_code).

    Mirrors download_bytes' TLS-retry ladder (SSRF-guarded via safe_stream,
    then OS-trust-store retry, then insecure retry) since range requests hit
    the same portal hosts with the same TLS quirks. Reads are capped the same
    way _download() caps a full download, rather than trusting the server to
    honor the Range header size -- a server that ignores Range and 200s the
    whole file must not be allowed to stream an unbounded response here.
    """

    async def _do(sess: httpx.AsyncClient) -> tuple[bytes, httpx.Headers, int]:
        # httpx offers gzip by default, and the SRI's download host (descargas.sri.gob.ec,
        # checked 2026-11-27) answers 200 with the whole file when it sees that offer,
        # then honors the same Range with 206 once the request says identity. Byte
        # offsets into a .zip mean the stored bytes, so identity is also the right ask.
        async with safe_stream(
            sess,
            url,
            timeout=_TIMEOUT,
            headers={"Range": range_header, "Accept-Encoding": "identity"},
        ) as resp:
            if resp.status_code not in (200, 206):
                resp.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                chunks.append(chunk)
                total += len(chunk)
                if total > cap:
                    break
            return b"".join(chunks)[:cap], resp.headers, resp.status_code

    own = session is None
    if own:
        session = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, proxy=proxy_for(url)
        )
    assert session is not None
    try:
        try:
            return await _do(session)
        except httpx.ConnectError as exc:
            if should_retry_with_os_trust(exc, url):
                logger.warning(
                    "TLS verification failed for %s: server didn't send its "
                    "intermediate CA; retrying with it bundled locally "
                    "(still fully verified)",
                    url,
                )
                async with httpx.AsyncClient(
                    headers={"User-Agent": USER_AGENT},
                    verify=os_trust_context(),
                    proxy=proxy_for(url),
                ) as os_trust_session:
                    return await _do(os_trust_session)
            if not should_retry_insecure(exc, url):
                raise
            logger.warning(
                "TLS verification failed for %s (portal cert expired); "
                "retrying without verification",
                url,
            )
            async with _insecure_client(url) as insecure_session:
                return await _do(insecure_session)
    finally:
        if own:
            await session.aclose()


async def _ranged(
    url: str,
    range_header: str,
    cap: int,
    session: httpx.AsyncClient | None,
    blob: bytes | SpooledBlob | None,
) -> tuple[bytes, httpx.Headers, int]:
    """_fetch_range, or the same answer served from `blob` (a whole .zip, kept
    in memory or in a temporary file).

    The in-memory answer is always a well-formed 206, so every check and parse
    built on the Range path runs unchanged on a zip that was downloaded whole.
    """
    if blob is None:
        return await _fetch_range(url, range_header, cap=cap, session=session)
    total = len(blob)
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
    if match is None or match.group(1) == match.group(2) == "":
        raise ValueError(f"Rango no válido: {range_header!r}.")
    first, last = match.groups()
    if first == "":  # suffix form: the last N bytes
        start, end = max(total - int(last), 0), total - 1
    else:
        start, end = int(first), min(int(last or total - 1), total - 1)
    if start >= total or end < start:
        raise ValueError(
            f"El .zip está corrupto (el rango {range_header} queda fuera del "
            f"archivo, de {total} bytes)."
        )
    body = blob[start : end + 1][:cap]
    return body, httpx.Headers({"content-range": f"bytes {start}-{end}/{total}"}), 206


def _no_range_zip_limit() -> int:
    """Cap for a .zip downloaded whole: 400 MB, or ECUADOR_MCP_NO_RANGE_ZIP_MB.

    The SRI's province RUC files are 2 to 156 MB on a host without Range. Up to
    20 MB they stay in memory; beyond that they go to a temporary file (and stay
    there for the 5-minute cache, up to two files), so the ceiling is a disk
    size, 1024 MB, that an operator can lower or raise.
    """
    raw = os.getenv(_NO_RANGE_ZIP_ENV, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return min(int(raw), _NO_RANGE_ZIP_MAX_MB) * 1024 * 1024
    return _MAX_NO_RANGE_ZIP_BYTES


async def _download_whole_zip(url: str, session: httpx.AsyncClient | None) -> SpooledBlob:
    """Download a .zip whose host does not support Range, up to the no-Range cap."""
    limit = _no_range_zip_limit()
    blob = SpooledBlob(_NO_RANGE_ZIP_RAM_BYTES)
    try:
        _empty, truncated = await asyncio.wait_for(
            download_bytes(url, session=session, max_bytes=limit, on_chunk=blob.write),
            timeout=_NO_RANGE_ZIP_DEADLINE_SECONDS,
        )
    except TimeoutError as exc:
        blob.close()
        raise ValueError(
            "El servidor no soporta HTTP Range y la descarga completa del .zip no "
            f"terminó en {int(_NO_RANGE_ZIP_DEADLINE_SECONDS)} s; reintenta en unos minutos."
        ) from exc
    except BaseException:
        blob.close()
        raise
    if truncated:
        blob.close()
        raise ValueError(
            "El servidor no soporta HTTP Range y este .zip pesa más de "
            f"{limit // (1024 * 1024)} MB, así que no se puede leer sin "
            "descargarlo completo. Descarga el enlace directo del archivo."
        )
    return blob


async def _zip_source(
    url: str, session: httpx.AsyncClient | None
) -> tuple[list[dict[str, Any]], int, int, bytes | SpooledBlob | None]:
    """Return (members, total_size, total_entries, blob) for a remote .zip.

    The central directory is read with Range requests (blob is None). When the
    host does not honor Range, the .zip is downloaded whole (see
    _MAX_NO_RANGE_ZIP_BYTES), in memory or in a temporary file, and kept for
    five minutes; blob holds those bytes and later reads of the same .zip are
    served from them. Only a Range failure triggers the fallback; any other
    error propagates.
    """
    blob = _blob_cache.get(url)
    if blob is None:
        try:
            members, total_size, entries = await _fetch_central_directory(url, session)
            return members, total_size, entries, None
        except _RangeUnsupported:
            lock = _zip_locks.get(url)
            if lock is None:
                lock = _zip_locks[url] = asyncio.Lock()
            async with lock:
                blob = _blob_cache.get(url)
                if blob is None:
                    logger.info("%s no soporta HTTP Range; descargando el .zip completo", url)
                    blob = await _download_whole_zip(url, session)
                    try:
                        members, total_size, entries = await _fetch_central_directory(
                            url, session, blob=blob
                        )
                    except BaseException:
                        blob.close()  # not a readable .zip: free the file now
                        raise
                    _blob_cache.set(url, blob)
                    if blob.on_disk:
                        # Free the temporary file when the entry expires, not
                        # only when another .zip happens to need the slot.
                        asyncio.get_running_loop().call_later(
                            _BLOB_CACHE_SECONDS + 5, _blob_cache.get, url
                        )
                    return members, total_size, entries, blob
    members, total_size, entries = await _fetch_central_directory(url, session, blob=blob)
    return members, total_size, entries, blob


def _parse_content_range(headers: httpx.Headers) -> tuple[int, int]:
    """Return (range_start, total_size) from a 206 response's Content-Range header."""
    header = headers.get("content-range")
    if not header:
        raise _RangeUnsupported(
            "El servidor no devolvió un rango parcial (falta el header "
            "Content-Range) -- no soporta HTTP Range requests, así que este "
            ".zip no se puede listar sin descargarlo completo."
        )
    m = _CONTENT_RANGE_RE.search(header)
    if not m:
        raise ValueError(f"Header Content-Range con formato inesperado: {header!r}")
    start, _end, total = (int(g) for g in m.groups())
    return start, total


def _parse_eocd(tail: bytes) -> tuple[int, int, int]:
    """Return (cd_offset, cd_size, total_entries) from the End Of Central
    Directory record found by scanning `tail` (the last bytes of a .zip)."""
    idx = tail.rfind(_EOCD_SIGNATURE)
    if idx == -1 or idx + 22 > len(tail):
        raise ValueError(
            "No se encontró el registro 'End Of Central Directory' -- puede "
            "que no sea un .zip válido."
        )
    _sig, _disk, _disk_start, _entries_disk, total_entries, cd_size, cd_offset, _comment_len = (
        struct.unpack_from("<4sHHHHIIH", tail, idx)
    )
    if total_entries == 0xFFFF or cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        raise _Zip64Required(idx)
    return cd_offset, cd_size, total_entries


class _Zip64Required(ValueError):
    """The classic EOCD holds ZIP64 sentinels; the real values live in the
    ZIP64 end-of-central-directory record found through its locator."""

    def __init__(self, eocd_index: int) -> None:
        super().__init__(
            "Este .zip usa ZIP64 (más de 65535 archivos o más de 4 GB) y no "
            "trae el registro ZIP64 que lo describe; parece corrupto."
        )
        self.eocd_index = eocd_index


_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_ZIP64_EOCD_SIGNATURE = b"PK\x06\x06"


async def _read_zip64_eocd(
    url: str,
    tail: bytes,
    tail_start: int,
    eocd_index: int,
    session: httpx.AsyncClient | None,
    blob: bytes | SpooledBlob | None = None,
) -> tuple[int, int, int]:
    """Return (cd_offset, cd_size, total_entries) from the ZIP64 EOCD record."""
    loc = eocd_index - 20
    if loc < 0 or tail[loc : loc + 4] != _ZIP64_LOCATOR_SIGNATURE:
        raise _Zip64Required(eocd_index)
    _sig, _disk, record_offset, _disks = struct.unpack_from("<4sIQI", tail, loc)

    if tail_start <= record_offset and record_offset + 56 <= tail_start + len(tail):
        record = tail[record_offset - tail_start : record_offset - tail_start + 56]
    else:
        record, headers, status = await _ranged(
            url,
            f"bytes={record_offset}-{record_offset + 55}",
            cap=56,
            session=session,
            blob=blob,
        )
        _check_partial(status, headers, record_offset)
    if len(record) < 56 or record[:4] != _ZIP64_EOCD_SIGNATURE:
        raise _Zip64Required(eocd_index)
    (_sig, _size, _made, _needed, _disk, _cd_disk, _entries_disk, total_entries,
     cd_size, cd_offset) = struct.unpack_from("<4sQHHIIQQQQ", record, 0)
    return cd_offset, cd_size, total_entries


def _decode_zip_name(raw: bytes, flags: int) -> str:
    """Decode a member name: UTF-8 when the archive says so, else cp850.

    The zip spec says cp437 for names without the UTF-8 flag, but the archivers
    on Spanish-language Windows (INEC's, for one) write the OEM code page 850.
    The two agree on lowercase accents and ñ, and differ on capitals: 0xD6 is
    "Í" in cp850 and a box-drawing "╓" in cp437, so "RÍOS" came out "R╓OS" in
    56 of the 507 INEC archives checked.
    """
    return raw.decode("utf-8" if flags & 0x0800 else "cp850", errors="replace")


def _nested_member_name(info: zipfile.ZipInfo) -> str:
    """The same name rule for zipfile, which always decodes non-UTF-8 as cp437."""
    if info.flag_bits & 0x0800:
        return info.filename
    return _decode_zip_name(info.filename.encode("cp437", errors="replace"), 0)


def _apply_zip64_extra(extra: bytes, sizes: dict[str, int]) -> None:
    """Replace 0xFFFFFFFF sizes/offset with the 8-byte values of extra field 0x0001.

    The ZIP64 extra field lists only the fields whose 32-bit slot holds the
    sentinel, in a fixed order: uncompressed size, compressed size, local
    header offset.
    """
    pos = 0
    while pos + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, pos)
        body = extra[pos + 4 : pos + 4 + size]
        pos += 4 + size
        if header_id != 0x0001:
            continue
        cursor = 0
        for key in ("uncompressed_size", "compressed_size", "local_header_offset"):
            if sizes[key] == 0xFFFFFFFF and cursor + 8 <= len(body):
                (sizes[key],) = struct.unpack_from("<Q", body, cursor)
                cursor += 8
        return


def _parse_central_directory(data: bytes, expected_entries: int) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    pos = 0
    while pos < len(data) and len(members) < expected_entries:
        # A short or hostile central directory must end the listing, not
        # surface as a struct.error from unpack_from.
        if pos + 46 > len(data) or data[pos : pos + 4] != _CD_HEADER_SIGNATURE:
            break
        (
            _sig,
            _made_by,
            _needed,
            flags,
            compression,
            _mtime,
            _mdate,
            crc32,
            compressed_size,
            uncompressed_size,
            name_len,
            extra_len,
            comment_len,
            _disk_start,
            _internal_attrs,
            _external_attrs,
            local_offset,
        ) = struct.unpack_from("<4sHHHHHHIIIHHHHHII", data, pos)
        pos += 46
        name = _decode_zip_name(data[pos : pos + name_len], flags)
        sizes = {
            "uncompressed_size": uncompressed_size,
            "compressed_size": compressed_size,
            "local_header_offset": local_offset,
        }
        if 0xFFFFFFFF in sizes.values():
            extra = data[pos + name_len : pos + name_len + extra_len]
            _apply_zip64_extra(extra, sizes)
            uncompressed_size = sizes["uncompressed_size"]
            compressed_size = sizes["compressed_size"]
            local_offset = sizes["local_header_offset"]
        pos += name_len + extra_len + comment_len
        members.append(
            {
                "name": name,
                "is_dir": name.endswith("/"),
                "compressed_size": compressed_size,
                "uncompressed_size": uncompressed_size,
                "compression": {0: "stored", 8: "deflate"}.get(
                    compression, str(compression)
                ),
                # Internal fields for read_zip_member; list_zip_contents
                # projects them out (_PUBLIC_MEMBER_KEYS).
                "compression_method": compression,
                "flags": flags,
                "crc32": crc32,
                "local_header_offset": local_offset,
            }
        )
    return members


_PUBLIC_MEMBER_KEYS = (
    "name",
    "is_dir",
    "compressed_size",
    "uncompressed_size",
    "compression",
)
_RANGE_UNSUPPORTED = (
    "El servidor no respondió con el rango pedido (HTTP 206 con el mismo "
    "inicio) -- no soporta HTTP Range requests, así que este .zip no se "
    "puede leer sin descargarlo completo."
)


async def _fetch_central_directory(
    url: str,
    session: httpx.AsyncClient | None = None,
    blob: bytes | SpooledBlob | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Return (members with internal fields, total_size, total_entries).

    Read with Range requests, or from `blob` when the .zip was downloaded whole.
    """
    tail, tail_headers, tail_status = await _ranged(
        url,
        f"bytes=-{_EOCD_TAIL_BYTES}",
        cap=_EOCD_TAIL_BYTES,
        session=session,
        blob=blob,
    )
    if tail_status != 206:
        raise _RangeUnsupported(
            "El servidor respondió con HTTP 200 en vez de 206 (Partial "
            "Content) -- no soporta HTTP Range requests, así que este .zip "
            "no se puede listar sin descargarlo completo."
        )
    tail_start, total_size = _parse_content_range(tail_headers)

    try:
        cd_offset, cd_size, total_entries = _parse_eocd(tail)
    except _Zip64Required as zip64:
        cd_offset, cd_size, total_entries = await _read_zip64_eocd(
            url, tail, tail_start, zip64.eocd_index, session, blob
        )

    if cd_offset >= tail_start:
        cd_data = tail[cd_offset - tail_start : cd_offset - tail_start + cd_size]
    else:
        if cd_size > _MAX_CENTRAL_DIR_BYTES:
            raise ValueError(
                f"El directorio central de este .zip pesa {cd_size} bytes, "
                f"por encima del límite de {_MAX_CENTRAL_DIR_BYTES} bytes "
                "que este listado soporta."
            )
        cd_data, _cd_headers, cd_status = await _ranged(
            url,
            f"bytes={cd_offset}-{cd_offset + cd_size - 1}",
            cap=_MAX_CENTRAL_DIR_BYTES,
            session=session,
            blob=blob,
        )
        if cd_status != 206:
            raise _RangeUnsupported(
                "El servidor respondió con HTTP 200 en vez de 206 (Partial "
                "Content) al pedir el directorio central -- no se puede "
                "listar este .zip sin descargarlo completo."
            )

    return _parse_central_directory(cd_data, total_entries), total_size, total_entries


async def list_zip_contents(
    url: str, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """
    List a .zip archive's members (name, size, compression) via HTTP Range
    requests, without downloading the archive itself.

    Works for archives far past MAX_DOWNLOAD_BYTES since only the End Of
    Central Directory record and the central directory itself are fetched --
    both tiny relative to the archive, proportional to entry count rather
    than entry content. Requires the server to honor Range requests (returns
    HTTP 206); raises ValueError otherwise. Reads ZIP64 end records and
    extra fields, so archives past 4 GB or 65535 entries list too.
    """
    members, total_size, total_entries, _blob = await _zip_source(url, session)
    return {
        "url": url,
        "total_size_bytes": total_size,
        "total_entries": total_entries,
        "members": [{k: m[k] for k in _PUBLIC_MEMBER_KEYS} for m in members],
    }


_ZIP_TEXT_EXTS = (".csv", ".tsv", ".txt")
_ZIP_SHEET_PARSERS: dict[str, Callable[..., dict[str, Any]]] = {
    ".xlsx": _parse_xlsx_bytes,
    ".xls": _parse_xls_bytes,
    ".xlsb": _parse_xlsb_bytes,
    ".ods": _parse_ods_bytes,
}
_LOCAL_HEADER_SIGNATURE = b"PK\x03\x04"
_LOCAL_HEADER_SLACK = 1024  # room for a local name/extra longer than the CD's


def _resolve_member(members: list[dict[str, Any]], member: str) -> dict[str, Any]:
    """Exact name, then a unique case-insensitive or basename match, else ValueError."""
    by_name = {m["name"]: m for m in members}
    if member in by_name:
        return by_name[member]

    wanted = member.casefold()
    for candidates in (
        [m for m in members if m["name"].casefold() == wanted],
        [
            m
            for m in members
            if m["name"].rsplit("/", 1)[-1].casefold() == wanted.rsplit("/", 1)[-1]
        ],
    ):
        if len(candidates) == 1:
            return candidates[0]

    names = [m["name"] for m in members if not m["is_dir"]]
    close = difflib.get_close_matches(member, names, n=5, cutoff=0.5)
    hint = ", ".join(close) if close else ", ".join(names[:5])
    raise ValueError(
        f"No hay ningún archivo '{member}' dentro del .zip. "
        f"¿Quisiste decir: {hint}? Usa list_zip_contents para ver los nombres exactos."
    )


def _check_partial(status: int, headers: httpx.Headers, expected_start: int) -> None:
    """Require a 206 whose Content-Range starts where we asked."""
    if status != 206:
        raise _RangeUnsupported(_RANGE_UNSUPPORTED)
    start, _total = _parse_content_range(headers)
    if start != expected_start:
        raise _RangeUnsupported(_RANGE_UNSUPPORTED)


def _ext_of(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    return "." + base.rsplit(".", 1)[-1].lower() if "." in base else ""


_ZIP_NESTED_EXTS = (".zip",)


def _check_readable_ext(name: str, ext: str, *, allow_zip: bool) -> None:
    allowed = (*_ZIP_TEXT_EXTS, *_ZIP_SHEET_PARSERS, *(_ZIP_NESTED_EXTS if allow_zip else ()))
    if ext not in allowed:
        raise ValueError(
            f"'{name}' no tiene un formato legible ({ext or 'sin extensión'}). "
            f"Formatos soportados: {', '.join(allowed)}."
        )


async def _parse_table_bytes(
    name: str,
    ext: str,
    out: bytes,
    truncated: bool,
    max_rows: int,
    skip_rows: int,
    sheet: str,
) -> dict[str, Any]:
    """Parse a text or spreadsheet file and tidy its report layout."""
    # Read past max_rows so a title block above the real header still leaves
    # max_rows data rows once it is skipped.
    parse_rows = max_rows + (_HEADER_SCAN_ROWS if skip_rows < 0 else skip_rows)
    if ext in _ZIP_SHEET_PARSERS:
        result = await run_parser_off_loop(
            _ZIP_SHEET_PARSERS[ext], out, parse_rows, False, sheet
        )
    else:
        if sheet.strip():
            raise ValueError(
                f"'{name}' es un archivo de texto ({ext}); el parámetro sheet solo "
                "aplica a hojas de cálculo."
            )
        result = _parse_csv_bytes(out, parse_rows, truncated=truncated)
        result["format"] = ext.lstrip(".")

    more = result["truncated"]
    tidy = _tidy_report_table([result["headers"], *result["rows"]], skip_rows)
    rows = tidy["rows"]
    result.update(
        {
            "headers": tidy["headers"],
            "rows": rows[:max_rows],
            "total_rows_in_preview": min(len(rows), max_rows),
            "truncated": more or len(rows) > max_rows,
            "header_row": tidy["header_row"],
            "preamble": tidy["preamble"],
            "dropped_empty_columns": tidy["dropped_empty_columns"],
        }
    )
    return result


def _read_nested_member(
    outer_name: str, outer: bytes, inner_member: str
) -> tuple[str, bytes, bool, int, int]:
    """Pick one file out of a .zip that was itself a member of the remote .zip.

    Returns (display name, bytes, truncated, compressed size, uncompressed
    size) of the inner file, so the caller reports the sizes of what it read.
    """
    _check_zip_container_size(outer, outer_name)
    try:
        zf = zipfile.ZipFile(io.BytesIO(outer))
    except zipfile.BadZipFile as e:
        raise ValueError(f"'{outer_name}' no es un .zip válido ({e}).") from e
    with zf:
        infos = zf.infolist()
        members = [
            {"name": _nested_member_name(i), "is_dir": i.is_dir(), "size": i.file_size}
            for i in infos
        ]
        zip_infos = {m["name"]: i for m, i in zip(members, infos, strict=True)}
        files = [m["name"] for m in members if not m["is_dir"]]
        if not inner_member.strip():
            listed = ", ".join(files[:50])
            more = f" (y {len(files) - 50} más)" if len(files) > 50 else ""
            raise ValueError(
                f"'{outer_name}' es un .zip dentro del .zip. Indica cuál de sus "
                f"archivos leer con inner_member: {listed}{more}."
            )
        info = _resolve_member(members, inner_member)
        name = info["name"]
        if info["is_dir"]:
            raise ValueError(f"'{name}' es una carpeta dentro de '{outer_name}'.")
        ext = _ext_of(name)
        _check_readable_ext(name, ext, allow_zip=False)
        is_sheet = ext in _ZIP_SHEET_PARSERS
        cap = _MAX_DECOMPRESSED_BYTES if is_sheet else MAX_DOWNLOAD_BYTES
        if is_sheet and info["size"] > cap:
            raise ValueError(
                f"'{name}' se expande a {info['size']} bytes, por encima del "
                f"límite de {cap // (1024 * 1024)} MB para hojas de cálculo."
            )
        with zf.open(zip_infos[name]) as fh:
            data = fh.read(cap + 1)
        truncated = len(data) > cap
        return (
            f"{outer_name}/{name}",
            data[:cap],
            truncated,
            zip_infos[name].compress_size,
            info["size"],
        )


async def _read_direct_file(
    url: str, session: httpx.AsyncClient | None
) -> tuple[str, str, bytes, bool, int]:
    """Download a spreadsheet or text file published directly at `url`."""
    path = urlsplit(url).path
    name = unquote(path.rsplit("/", 1)[-1]) or url
    ext = _ext_of(path)
    _check_readable_ext(name, ext, allow_zip=False)
    is_sheet = ext in _ZIP_SHEET_PARSERS
    cap = _MAX_DECOMPRESSED_BYTES if is_sheet else MAX_DOWNLOAD_BYTES
    raw, truncated = await download_bytes(url, session=session, max_bytes=cap)
    if is_sheet and truncated:
        raise ValueError(
            f"'{name}' supera el límite de {cap // (1024 * 1024)} MB; una hoja de "
            "cálculo no se puede abrir incompleta."
        )
    return name, ext, raw, truncated, len(raw)


async def read_zip_member(
    url: str,
    member: str,
    max_rows: int = 50,
    session: httpx.AsyncClient | None = None,
    skip_rows: int = -1,
    sheet: str = "",
    inner_member: str = "",
) -> dict[str, Any]:
    """Read one member of a remote .zip by fetching only that member's bytes.

    `skip_rows`: rows above the column header (-1 detects it, see
    _tidy_report_table). Empty columns are dropped from the result.
    `sheet`: for spreadsheets, a sheet name or 1-based number ("" = the
    workbook's active/first sheet). The result lists every sheet in `sheets`.
    `inner_member`: when `member` is itself a .zip (INEC publishes CSV
    tabulados as a zip of zips), the file to read inside it.
    An empty `member` reads `url` itself as a spreadsheet or text file
    (e.g. a .xlsx published directly, outside any .zip).

    Uses the central directory (as list_zip_contents does) to locate the
    member, then Range-fetches its local header and compressed data. Caps:
    a CSV/text member of any size is read from its first MAX_DOWNLOAD_BYTES
    (compressed) and its output stops at MAX_DOWNLOAD_BYTES (marked
    truncated); spreadsheets and nested .zip members are opened whole, so
    they must fit in _MAX_DECOMPRESSED_BYTES both compressed and expanded.
    Only stored and deflate members, no encryption; ZIP64 is supported.
    """
    if not member.strip():
        if inner_member.strip():
            raise ValueError(
                "inner_member solo aplica a un .zip dentro del .zip; con member='' "
                "se lee la URL misma."
            )
        name, ext, out, truncated, size = await _read_direct_file(url, session)
        result = await _parse_table_bytes(
            name, ext, out, truncated, max_rows, skip_rows, sheet
        )
        result.update(
            {
                "member_name": name,
                "compressed_size": size,
                "uncompressed_size": size,
                "url": url,
            }
        )
        return result

    members, total_size, _entries, blob = await _zip_source(url, session)
    info = _resolve_member(members, member)
    name = info["name"]

    if info["is_dir"]:
        raise ValueError(f"'{name}' es una carpeta dentro del .zip, no un archivo.")
    if info["flags"] & 0x1:
        raise ValueError(f"'{name}' está cifrado con contraseña; no se puede leer.")
    method = info["compression_method"]
    if method not in (0, 8):
        raise ValueError(
            f"'{name}' usa un método de compresión no soportado ({method}); "
            "solo se leen miembros sin comprimir (stored) o deflate."
        )
    if 0xFFFFFFFF in (
        info["compressed_size"],
        info["uncompressed_size"],
        info["local_header_offset"],
    ):
        raise ValueError(
            f"'{name}': el .zip está corrupto (tamaño ZIP64 sin su campo extra)."
        )
    compressed_size = info["compressed_size"]

    ext = _ext_of(name)
    _check_readable_ext(name, ext, allow_zip=True)
    is_nested = ext in _ZIP_NESTED_EXTS
    if inner_member.strip() and not is_nested:
        raise ValueError(
            f"'{name}' no es un .zip; inner_member solo aplica a un .zip dentro del .zip."
        )
    # Spreadsheets and nested zips are opened whole, so they must be complete
    # and fit the 20 MB cap, compressed (what is downloaded) and expanded.
    is_sheet = ext in _ZIP_SHEET_PARSERS or is_nested
    if is_sheet and compressed_size > _MAX_DECOMPRESSED_BYTES:
        raise ValueError(
            f"'{name}' pesa {compressed_size} bytes comprimido, por encima del "
            f"límite de {_MAX_DECOMPRESSED_BYTES // (1024 * 1024)} MB para hojas de "
            "cálculo y .zip internos. Descarga el .zip directamente."
        )
    if is_sheet and info["uncompressed_size"] > _MAX_DECOMPRESSED_BYTES:
        raise ValueError(
            f"'{name}' se expande a {info['uncompressed_size']} bytes, por encima "
            f"del límite de {_MAX_DECOMPRESSED_BYTES // (1024 * 1024)} MB para hojas "
            "de cálculo y .zip internos."
        )
    # Text is only previewed, so a member of any size is readable from its first
    # bytes: fetch at most MAX_DOWNLOAD_BYTES of it and mark the result truncated.
    head_only = not is_sheet and compressed_size > MAX_DOWNLOAD_BYTES
    fetch_size = MAX_DOWNLOAD_BYTES if head_only else compressed_size

    # One request: local header, the central directory's name/extra length
    # plus slack (the local extra field can differ), and the data itself.
    start = info["local_header_offset"]
    if start + 30 > total_size:
        raise ValueError(f"'{name}': el .zip está corrupto (offset fuera del archivo).")
    guess_len = 30 + len(name.encode("utf-8")) + _LOCAL_HEADER_SLACK + fetch_size
    end = min(start + guess_len, total_size) - 1
    buf, headers, status = await _ranged(
        url, f"bytes={start}-{end}", cap=end - start + 1, session=session, blob=blob
    )
    _check_partial(status, headers, start)
    if len(buf) < 30 or buf[:4] != _LOCAL_HEADER_SIGNATURE:
        raise ValueError(f"'{name}': el .zip está corrupto (cabecera local inválida).")
    local_name_len, local_extra_len = struct.unpack_from("<HH", buf, 26)
    data_start = start + 30 + local_name_len + local_extra_len
    data_end = data_start + fetch_size

    if data_end <= start + len(buf):
        data = buf[data_start - start : data_end - start]
    else:
        data, headers, status = await _ranged(
            url,
            f"bytes={data_start}-{data_end - 1}",
            cap=fetch_size,
            session=session,
            blob=blob,
        )
        _check_partial(status, headers, data_start)
    if len(data) != fetch_size:
        raise ValueError(f"'{name}': el .zip está corrupto (datos incompletos).")

    cap = _MAX_DECOMPRESSED_BYTES if is_sheet else MAX_DOWNLOAD_BYTES
    if method == 0:
        out, truncated = data[:cap], len(data) > cap
    else:
        try:
            out, truncated = _inflate_capped(data, -zlib.MAX_WBITS, cap)
        except zlib.error as e:
            raise ValueError(f"'{name}': el .zip está corrupto ({e}).") from e
    # A head is cut by construction, even when it inflates to under the cap.
    truncated = truncated or head_only

    complete = not truncated and len(out) == info["uncompressed_size"]
    if not truncated and not complete:
        raise ValueError(
            f"'{name}': el .zip está corrupto (tamaño descomprimido inesperado)."
        )
    if complete and zlib.crc32(out) != info["crc32"]:
        raise ValueError(f"'{name}': el .zip está corrupto (CRC32 no coincide).")
    if is_sheet and not complete:
        raise ValueError(
            f"'{name}' supera el límite de {_MAX_DECOMPRESSED_BYTES // (1024 * 1024)} MB "
            "descomprimido; una hoja de cálculo no se puede abrir incompleta."
        )

    read_name = name
    sizes = (compressed_size, info["uncompressed_size"])
    if is_nested:
        # Decompressing up to 20 MB is blocking work: keep it off the event loop.
        read_name, out, truncated, *inner_sizes = await run_parser_off_loop(
            _read_nested_member, name, out, inner_member
        )
        sizes = (inner_sizes[0], inner_sizes[1])
        ext = _ext_of(read_name)

    result = await _parse_table_bytes(
        read_name, ext, out, truncated, max_rows, skip_rows, sheet
    )
    result.update(
        {
            "member_name": read_name,
            "compressed_size": sizes[0],
            "uncompressed_size": sizes[1],
            "url": url,
        }
    )
    if is_nested:
        # member_name and the sizes describe the inner file that was read.
        result["outer_member"] = name
    return result



@dataclass(frozen=True)
class ZipMemberSpan:
    """A text member of a remote .zip whose compressed bytes can be read here.

    `source[offset : offset + compressed_size]` is the member's stored or
    deflate data: the whole .zip held by a host without Range, or the member
    alone, fetched with Range requests into a temporary file (offset 0).
    """

    name: str
    method: int
    compressed_size: int
    uncompressed_size: int
    crc32: int
    source: bytes | SpooledBlob
    offset: int


_SPAN_REQUEST_BYTES = 8 * 1024 * 1024
_SPAN_DEADLINE_SECONDS = 600.0
_STREAM_READ_BYTES = 1024 * 1024
_STREAM_OUT_BYTES = 4 * 1024 * 1024


async def _spool_member_data(
    url: str, start: int, end: int, session: httpx.AsyncClient | None
) -> SpooledBlob:
    """Range-fetch bytes [start, end) of a remote .zip into a SpooledBlob."""
    spool = SpooledBlob(_NO_RANGE_ZIP_RAM_BYTES)
    # One connection for the whole span, not a TLS handshake per request.
    own = session is None
    if own:
        session = httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, proxy=proxy_for(url))
    try:
        position = start
        while position < end:
            last = min(position + _SPAN_REQUEST_BYTES, end) - 1
            chunk, headers, status = await _ranged(
                url, f"bytes={position}-{last}", cap=last - position + 1, session=session, blob=None
            )
            _check_partial(status, headers, position)
            if len(chunk) != last - position + 1:
                raise ValueError("El .zip está corrupto (datos incompletos).")
            spool.write(chunk)
            position = last + 1
    except BaseException:
        spool.close()
        raise
    finally:
        if own and session is not None:
            await session.aclose()
    return spool


async def locate_zip_member(
    url: str,
    member: str,
    *,
    max_compressed: int,
    max_uncompressed: int,
    session: httpx.AsyncClient | None = None,
) -> ZipMemberSpan:
    """Find a CSV/TSV/TXT member of a remote .zip and get its bytes within reach.

    Meant for reading the whole member (iter_zip_member), however large: a
    member over `max_compressed` or `max_uncompressed` bytes is refused rather
    than read in part. A host that honors Range sends only this member's
    compressed bytes, to a temporary file; one that does not has already
    handed over the whole .zip (see _zip_source).
    """
    members, total_size, _entries, blob = await _zip_source(url, session)
    info = _resolve_member(members, member)
    name = info["name"]
    if info["is_dir"]:
        raise ValueError(f"'{name}' es una carpeta dentro del .zip, no un archivo.")
    if info["flags"] & 0x1:
        raise ValueError(f"'{name}' está cifrado con contraseña; no se puede leer.")
    method = info["compression_method"]
    if method not in (0, 8):
        raise ValueError(
            f"'{name}' usa un método de compresión no soportado ({method}); "
            "solo se leen miembros sin comprimir (stored) o deflate."
        )
    compressed_size = info["compressed_size"]
    uncompressed_size = info["uncompressed_size"]
    if 0xFFFFFFFF in (compressed_size, uncompressed_size, info["local_header_offset"]):
        raise ValueError(f"'{name}': el .zip está corrupto (tamaño ZIP64 sin su campo extra).")
    ext = _ext_of(name)
    if ext not in _ZIP_TEXT_EXTS:
        raise ValueError(
            f"'{name}' no es texto delimitado ({ext or 'sin extensión'}); este tool lee "
            f"{', '.join(_ZIP_TEXT_EXTS)}. Una hoja de cálculo va por read_zip_member."
        )
    for size, limit, what in (
        (compressed_size, max_compressed, "comprimido"),
        (uncompressed_size, max_uncompressed, "descomprimido"),
    ):
        if size > limit:
            raise ValueError(
                f"'{name}' pesa {size / (1024 * 1024):,.0f} MB {what}, por encima del "
                f"límite de {limit // (1024 * 1024)} MB: sumarlo incompleto daría "
                "totales falsos, así que no se lee."
            )

    start = info["local_header_offset"]
    if start + 30 > total_size:
        raise ValueError(f"'{name}': el .zip está corrupto (offset fuera del archivo).")
    header, headers, status = await _ranged(
        url, f"bytes={start}-{start + 29}", cap=30, session=session, blob=blob
    )
    _check_partial(status, headers, start)
    if len(header) < 30 or header[:4] != _LOCAL_HEADER_SIGNATURE:
        raise ValueError(f"'{name}': el .zip está corrupto (cabecera local inválida).")
    local_name_len, local_extra_len = struct.unpack_from("<HH", header, 26)
    data_start = start + 30 + local_name_len + local_extra_len
    data_end = data_start + compressed_size
    if data_end > total_size:
        raise ValueError(f"'{name}': el .zip está corrupto (datos fuera del archivo).")

    if blob is not None:
        source: bytes | SpooledBlob = blob
        offset = data_start
    else:
        try:
            source = await asyncio.wait_for(
                _spool_member_data(url, data_start, data_end, session),
                timeout=_SPAN_DEADLINE_SECONDS,
            )
        except TimeoutError as exc:
            raise ValueError(
                f"La descarga de '{name}' no terminó en {int(_SPAN_DEADLINE_SECONDS)} s; "
                "reintenta en unos minutos."
            ) from exc
        offset = 0
    return ZipMemberSpan(
        name=name,
        method=method,
        compressed_size=compressed_size,
        uncompressed_size=uncompressed_size,
        crc32=info["crc32"],
        source=source,
        offset=offset,
    )


def iter_zip_member(span: ZipMemberSpan) -> Iterator[bytes]:
    """Yield a member's decompressed bytes in chunks, whatever its size.

    Blocking (disk reads, zlib): run it in a thread. Memory stays at a few
    megabytes, and no more output than the declared size is accepted, so a
    member that expands past it fails instead of filling the disk or memory.
    Once the data ends the size and the CRC32 are checked, so a damaged .zip
    raises ValueError rather than giving a total over wrong rows.
    """
    name = span.name
    corrupt = f"'{name}': el .zip está corrupto"
    inflater = zlib.decompressobj(-zlib.MAX_WBITS) if span.method == 8 else None
    produced = 0
    crc = 0
    position = span.offset
    end = span.offset + span.compressed_size

    def checked(out: bytes) -> bytes:
        nonlocal produced, crc
        produced += len(out)
        if produced > span.uncompressed_size:
            raise ValueError(f"{corrupt} (más datos que el tamaño declarado).")
        crc = zlib.crc32(out, crc)
        return out

    while position < end:
        raw = span.source[position : min(position + _STREAM_READ_BYTES, end)]
        if not raw:
            raise ValueError(f"{corrupt} (datos incompletos).")
        position += len(raw)
        if inflater is None:
            yield checked(raw)
            continue
        pending = raw
        while pending:
            before = len(pending)
            try:
                out = inflater.decompress(pending, _STREAM_OUT_BYTES)
            except zlib.error as exc:
                raise ValueError(f"{corrupt} ({exc}).") from exc
            pending = inflater.unconsumed_tail
            if out:
                yield checked(out)
            elif len(pending) >= before:
                raise ValueError(f"{corrupt} (flujo deflate detenido).")
    if inflater is not None:
        try:
            out = inflater.flush()
        except zlib.error as exc:
            raise ValueError(f"{corrupt} ({exc}).") from exc
        if out:
            yield checked(out)
        if not inflater.eof:
            raise ValueError(f"{corrupt} (datos incompletos).")
    if produced != span.uncompressed_size:
        raise ValueError(f"{corrupt} (tamaño descomprimido inesperado).")
    if crc != span.crc32:
        raise ValueError(f"{corrupt} (CRC32 no coincide).")


_HEADER_SCAN_ROWS = 30
_PREAMBLE_MAX_ROWS = 10


def _unwrap_quoted_line(row: list[str]) -> list[str]:
    """Split a row whose whole line was quoted into one cell.

    INEC's tabulados (ENDI R3, 2026-11-07) quote some entire lines, e.g.
    the line for Nacional starts with a quote and keeps its own thousands
    ("4,288") as doubled quotes inside, so the CSV reader returns the
    line as a single cell. Re-parse that cell when it clearly holds several
    fields; a lone title with a comma ("..., que están") is left alone.
    """
    cells = [c for c in row if c.strip()]
    if len(cells) != 1 or row[0] != cells[0]:
        return row
    text = cells[0]
    delimiter = _sniff_delimiter(text)
    if delimiter not in text:
        return row
    try:
        fields = next(csv.reader([text], delimiter=delimiter))
    except (csv.Error, StopIteration):
        return row
    filled = [f for f in fields if f.strip()]
    if len(filled) >= 3 or (len(filled) >= 2 and '"' in text):
        return fields
    return row


def _tidy_report_table(table: list[list[str]], skip_rows: int) -> dict[str, Any]:
    """Find the real header in a report-style table and drop empty columns.

    Statistical tabulados (INEC, BCE) open with a title block -- table
    number, indicator, population, source -- before the column header, and
    often carry hundreds of empty trailing columns. `skip_rows` < 0 detects
    the header as the first row at least half as full as the fullest of the
    first _HEADER_SCAN_ROWS rows; 0 keeps row 1; n skips n rows. A normal
    CSV, whose first row is already the fullest, comes back unchanged.
    """
    table = [_unwrap_quoted_line(row) for row in table]
    if skip_rows >= 0:
        header_row = min(skip_rows, max(len(table) - 1, 0))
    else:
        counts = [sum(1 for c in row if c.strip()) for row in table[:_HEADER_SCAN_ROWS]]
        fullest = max(counts, default=0)
        header_row = 0
        if fullest >= 2 and counts[0] * 2 < fullest:
            header_row = next(i for i, n in enumerate(counts) if n * 2 >= fullest)

    preamble = [
        " | ".join(c.strip() for c in row if c.strip())[:300]
        for row in table[:header_row]
        if any(c.strip() for c in row)
    ][:_PREAMBLE_MAX_ROWS]
    body = table[header_row:]
    if not body:
        return {
            "headers": [],
            "rows": [],
            "header_row": header_row,
            "preamble": preamble,
            "dropped_empty_columns": 0,
        }

    width = max(len(row) for row in body)
    keep = [
        i
        for i in range(width)
        if any(i < len(row) and row[i].strip() for row in body)
    ]
    trimmed = [[row[i] if i < len(row) else "" for i in keep] for row in body]
    return {
        "headers": trimmed[0],
        "rows": trimmed[1:],
        "header_row": header_row,
        "preamble": preamble,
        "dropped_empty_columns": width - len(keep),
    }


def format_table(headers: list[str], rows: list[list[str]], max_col_width: int = 40) -> str:
    """Format headers and rows as a readable text table."""
    if not headers:
        return "No data available."

    def trunc(val: str) -> str:
        val = val.strip()
        return val[:max_col_width] + "..." if len(val) > max_col_width else val

    display_headers = [trunc(h) for h in headers]
    display_rows = [[trunc(cell) for cell in row] for row in rows]

    ncols = len(display_headers)
    for row in display_rows:
        while len(row) < ncols:
            row.append("")

    col_widths = [len(h) for h in display_headers]
    for row in display_rows:
        for i, cell in enumerate(row[:ncols]):
            col_widths[i] = max(col_widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return " | ".join(
            cell.ljust(col_widths[i]) for i, cell in enumerate(cells[:ncols])
        )

    lines = [fmt_row(display_headers)]
    lines.append("-+-".join("-" * w for w in col_widths))
    for row in display_rows:
        lines.append(fmt_row(row))

    return "\n".join(lines)

"""Total, count and group a delimited text file by reading all of it.

`read_zip_member` and `preview_resource_data` show the head of a file, at most
5 MB. That is a sample, not an answer, when the question is a total by group
(SRI sales by province and year) or when the file is only a little bigger than
the cap: each SRI "ventas" CSV is about 5.5 MB, so the head leaves out the last
tenth of the rows and nothing else can page through the rest.

This downloads the file whole (up to `MAX_BYTES`), parses it in a worker thread
and keeps only the group totals. Numbers are summed as `Decimal`, so a total of
hundreds of billions with four decimals does not pick up float noise.
"""

from __future__ import annotations

import asyncio
import codecs
import copy
import csv
import io
import itertools
import json
from collections import defaultdict
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes, run_parser_off_loop
from helpers.text_utils import strip_accents

MAX_BYTES = 30 * 1024 * 1024
MAX_GROUPS = 100_000
_DOWNLOAD_DEADLINE_SECONDS = 75.0
_DELIMITERS = (",", "|", ";", "\t")
_NOT_TEXT_EXTENSIONS = {
    ".zip": "es un .zip; usa list_zip_contents y read_zip_member",
    ".xlsx": "es una hoja de cálculo; usa read_zip_member con member=''",
    ".xls": "es una hoja de cálculo; usa read_zip_member con member=''",
    ".xlsb": "es una hoja de cálculo; usa read_zip_member con member=''",
    ".ods": "es una hoja de cálculo; usa read_zip_member con member=''",
    ".gz": "está comprimido; este tool lee texto plano",
    ".pdf": "es un PDF; usa read_pdf",
    ".json": "es JSON, no una tabla delimitada",
}

# The same file with the same arguments is answered from memory: an agent often
# repeats a call while it narrows a question. Short, because the SRI refreshes
# the current year's file monthly.
_cache = TtlCache(ttl_seconds=1800.0, max_entries=64, stale_seconds=0.0)


def parse_number(text: str) -> Decimal | None:
    """Read a number written with a decimal comma or a decimal point.

    "194488,1500", "194488.1500" and "1.234,56" all parse; ",0000" is zero. With
    both separators the last one is the decimal mark. A single comma is a
    decimal mark ("1,234" is 1.234), several commas are thousands separators.
    Returns None for anything else (text, "n/d", NaN), so the caller can count
    it instead of guessing a zero.
    """
    value = text.strip().replace(" ", "").replace(" ", "").lstrip("$")
    if not value or value in {"-", ".", ","}:
        return None
    commas, dots = value.count(","), value.count(".")
    if commas and dots:
        decimal_mark = "," if value.rfind(",") > value.rfind(".") else "."
        thousands = "." if decimal_mark == "," else ","
        value = value.replace(thousands, "").replace(decimal_mark, ".")
    elif commas:
        value = value.replace(",", ".") if commas == 1 else value.replace(",", "")
    elif dots > 1:
        value = value.replace(".", "")
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _norm_name(text: str) -> str:
    """AÑO, año and ANO match; so do CODIGO_SECTOR_N1 and 'codigo sector n1'."""
    folded = strip_accents(text)
    return "_".join("".join(c if c.isalnum() else " " for c in folded).split())


def _norm_value(text: str) -> str:
    return " ".join(strip_accents(text).split())


def _resolve_columns(requested: list[str], headers: list[str], label: str) -> list[int]:
    by_name: dict[str, int] = {}
    for position, header in enumerate(headers):
        by_name.setdefault(_norm_name(header), position)
    positions = []
    for name in requested:
        position = by_name.get(_norm_name(name))
        if position is None:
            raise ValueError(
                f"No hay una columna '{name}' (en {label}). "
                f"Columnas del archivo: {', '.join(headers)}."
            )
        positions.append(position)
    return positions


def _detect_encoding(raw: bytes) -> str:
    # A head cut inside a multibyte character is not a reason to give up on UTF-8.
    try:
        codecs.getincrementaldecoder("utf-8")().decode(raw[:65536], final=False)
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8-sig"


def _pick_delimiter(header_line: str) -> str:
    best = max(_DELIMITERS, key=header_line.count)
    return best if header_line.count(best) else ","


def _sort_key(value: Any) -> tuple[int, Any]:
    """Numbers before text, numbers by value (so month 2 comes before 10)."""
    if isinstance(value, int | float):
        return 0, Decimal(str(value))
    number = parse_number(value)
    return (0, number) if number is not None else (1, _norm_value(value))


def _rows(reader: Any) -> Iterator[list[str]]:
    try:
        yield from reader
    except csv.Error as exc:
        raise ValueError(f"El archivo no se pudo leer como tabla delimitada: {exc}.") from exc


def aggregate_bytes(
    raw: bytes,
    *,
    group_by: list[str],
    sum_columns: list[str],
    filters: dict[str, list[str]],
    order_by: str = "",
    limit: int = 50,
    skip_rows: int = 0,
) -> dict[str, Any]:
    """Group the rows of a delimited text file and total its numeric columns.

    `filters` keeps the rows whose cell equals one of the listed values, ignoring
    case and accents, or equals it as a number ("1" matches "01"). The header is
    the first line after `skip_rows` physical lines. Blank cells and cells that
    are not numbers are left out of the totals and counted in the result.
    """
    stream = io.TextIOWrapper(
        io.BytesIO(raw), encoding=_detect_encoding(raw), errors="replace", newline=""
    )
    for _ in range(max(skip_rows, 0)):
        stream.readline()
    header_line = stream.readline()
    if not header_line.strip():
        raise ValueError("El archivo está vacío o no tiene encabezado.")
    delimiter = _pick_delimiter(header_line)
    reader = csv.reader(itertools.chain([header_line], stream), delimiter=delimiter)
    headers = [cell.strip() for cell in next(reader)]

    group_at = _resolve_columns(group_by, headers, "group_by")
    sum_at = _resolve_columns(sum_columns, headers, "sum_columns")
    filter_specs = []
    for name, wanted in filters.items():
        (position,) = _resolve_columns([name], headers, "filters_json")
        texts = {_norm_value(v) for v in wanted}
        numbers = {n for n in (parse_number(v) for v in wanted) if n is not None}
        filter_specs.append((position, texts, numbers))

    counts: dict[tuple[str, ...], int] = defaultdict(int)
    totals: dict[tuple[str, ...], list[Decimal]] = {}
    blank = [0] * len(sum_at)
    not_numeric = [0] * len(sum_at)
    rows_read = rows_matched = 0
    width = len(headers)

    for row in _rows(reader):
        if not row or not any(cell.strip() for cell in row):
            continue
        rows_read += 1
        if len(row) < width:
            row = row + [""] * (width - len(row))
        if any(
            _norm_value(row[position]) not in texts
            and (parse_number(row[position]) not in numbers)
            for position, texts, numbers in filter_specs
        ):
            continue
        rows_matched += 1
        key = tuple(row[position].strip() for position in group_at)
        if key not in totals:
            if len(totals) >= MAX_GROUPS:
                raise ValueError(
                    f"Hay más de {MAX_GROUPS:,} grupos distintos: agrupa por menos "
                    "columnas o filtra con filters_json."
                )
            totals[key] = [Decimal(0)] * len(sum_at)
        counts[key] += 1
        for slot, position in enumerate(sum_at):
            text = row[position].strip()
            if not text:
                blank[slot] += 1
                continue
            number = parse_number(text)
            if number is None:
                not_numeric[slot] += 1
                continue
            totals[key][slot] += number

    keys = list(totals)
    group_headers = [headers[position] for position in group_at]
    sum_headers = [headers[position] for position in sum_at]
    output_headers = [*group_headers, "filas", *sum_headers]

    def cell_values(key: tuple[str, ...]) -> list[Any]:
        return [*key, counts[key], *(float(total) for total in totals[key])]

    sort_column, descending = _read_order(order_by, output_headers, len(group_at), bool(sum_at))
    rows_out = sorted(
        (cell_values(key) for key in keys),
        key=lambda cells: _sort_key(cells[sort_column]),
        reverse=descending,
    )

    grand = [sum((totals[key][slot] for key in keys), Decimal(0)) for slot in range(len(sum_at))]
    return {
        "headers": output_headers,
        "rows": rows_out[:limit],
        "grupos": len(keys),
        "filas_leidas": rows_read,
        "filas_coinciden": rows_matched,
        "totales": {"filas": rows_matched, **dict(zip(sum_headers, map(float, grand), strict=True))},
        "celdas_vacias": {h: n for h, n in zip(sum_headers, blank, strict=True) if n},
        "celdas_no_numericas": {h: n for h, n in zip(sum_headers, not_numeric, strict=True) if n},
        "columnas": headers,
        "delimitador": delimiter,
        "truncated": len(keys) > limit,
    }


def _read_order(
    order_by: str, output_headers: list[str], group_count: int, has_sums: bool
) -> tuple[int, bool]:
    """(column position, descending). Default: biggest first total, else most rows.

    Result columns are the group columns, then "filas", then the totals.
    """
    text = order_by.strip()
    if not text:
        return group_count + (1 if has_sums else 0), True
    direction = None
    parts = text.rsplit(None, 1)
    if len(parts) == 2 and parts[1].lower() in {"asc", "desc"}:
        text, direction = parts[0], parts[1].lower()
    wanted = _norm_name(text)
    for position, header in enumerate(output_headers):
        if _norm_name(header) == wanted:
            # A group column reads best ascending, a count or a total descending.
            descending = direction == "desc" if direction else position >= group_count
            return position, descending
    raise ValueError(
        f"order_by '{order_by}' no es una columna del resultado: "
        f"{', '.join(output_headers)}."
    )


def _check_url(url: str) -> None:
    path = urlsplit(url).path.lower()
    for extension, reason in _NOT_TEXT_EXTENSIONS.items():
        if path.endswith(extension):
            raise ValueError(f"Este archivo {reason}.")


def _check_payload(raw: bytes) -> None:
    if raw[:4] == b"PK\x03\x04":
        raise ValueError(
            "El archivo es un .zip o una hoja de cálculo, no texto; usa "
            "list_zip_contents y read_zip_member."
        )
    if raw[:1] == b"\x1f" and raw[1:2] == b"\x8b":
        raise ValueError("El archivo está comprimido (gzip); este tool lee texto plano.")
    if raw.lstrip()[:1] == b"<":
        raise ValueError(
            "La URL devolvió una página web, no un archivo de datos; revisa el enlace."
        )


async def aggregate_url(
    url: str,
    *,
    group_by: list[str],
    sum_columns: list[str],
    filters: dict[str, list[str]],
    order_by: str = "",
    limit: int = 50,
    skip_rows: int = 0,
) -> dict[str, Any]:
    """Download `url` whole and aggregate it; see `aggregate_bytes`."""
    _check_url(url)
    key = (
        url,
        tuple(group_by),
        tuple(sum_columns),
        json.dumps(filters, sort_keys=True, ensure_ascii=False),
        order_by,
        limit,
        skip_rows,
    )
    cached = _cache.get(key)
    if cached is not None:
        return copy.deepcopy(cached)

    try:
        raw, truncated = await asyncio.wait_for(
            download_bytes(url, max_bytes=MAX_BYTES), timeout=_DOWNLOAD_DEADLINE_SECONDS
        )
    except TimeoutError as exc:
        raise ValueError(
            f"La descarga no terminó en {int(_DOWNLOAD_DEADLINE_SECONDS)} s; "
            "reintenta en unos minutos."
        ) from exc
    if truncated:
        raise ValueError(
            f"El archivo pesa más de {MAX_BYTES // (1024 * 1024)} MB; sumarlo "
            "incompleto daría totales falsos, así que no se lee."
        )
    _check_payload(raw)

    result = await run_parser_off_loop(
        aggregate_bytes,
        raw,
        group_by=group_by,
        sum_columns=sum_columns,
        filters=filters,
        order_by=order_by,
        limit=limit,
        skip_rows=skip_rows,
    )
    result["bytes_leidos"] = len(raw)
    _cache.set(key, copy.deepcopy(result))
    return result

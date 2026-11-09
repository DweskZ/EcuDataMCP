"""Build/refresh the committed index of the Census 2022 tabulados.

`search_archivos(fuente="censo")` lists ~100 files, but a file name such as
"Dificultades funcionales" says little about which tables sit inside. This
reads each tabulado workbook (XLSX) from /resultados-censo/ and records, per
sheet, the table title, the geographic levels and the column headers, then
writes them to `helpers/data/censo_tabulados_index.json` together with the
source URL, SHA-256 and extraction date of every file. The server only reads
that JSON (see helpers/censo_index.py); it never downloads a workbook while
answering a query.

Lives in helpers/ (like supercias_financials_build) so installs without
scripts/ (PyPI, MCPB bundles) can run it:

    uv run python scripts/build_censo_index.py
    python -m helpers.censo_index_build [--out PATH] [--max-mb 25]

Workbooks above --max-mb are skipped and listed under "omitidos" in the JSON
(and logged); the download is bounded, so an oversized file is never pulled in
full. The tabulados follow one layout: an "Índice" sheet listing the tables,
then one sheet per table whose row 4 reads "Nombre de la tabla: <title>" and
whose header row starts with "Índice".
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from helpers.censo_index import INDEX_PATH
from helpers.text_utils import strip_accents

logger = logging.getLogger("ecuador_mcp.censo_index_build")

DEFAULT_MAX_MB = 25
# Rows read from the top of each sheet: title block (rows 3-6) + header (9-10).
_HEAD_ROWS = 16
_MAX_COLUMNS = 10
_MAX_TEXT = 140
_TITLE_LABEL = re.compile(r"^(nombre\s+de(l|\s+la)\s+(tabla|cuadro)|t[ií]tulo)\b", re.IGNORECASE)
_NUMBER_LABEL = re.compile(r"^(tabla|cuadro)\s*\.?\s*n", re.IGNORECASE)
_TABLE_ID = re.compile(r"^\d+(\.\d+)*$")
_LEVELS = (
    ("nacional", "nacional"),
    ("provincia", "provincia"),
    ("canton", "cantón"),
    ("parroquia", "parroquia"),
)


def _text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _is_number(value: Any) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    return bool(re.fullmatch(r"-?[\d.,]+%?", _text(value))) and bool(_text(value))


def detect_levels(*texts: str) -> list[str]:
    """Geographic levels named in the given titles/headers, coarse to fine."""
    blob = strip_accents(" ".join(texts)).lower()
    return [label for key, label in _LEVELS if key in blob]


def _index_titles(rows: list[tuple[Any, ...]]) -> dict[str, str]:
    """`Tabla.N° / Contenido` rows of the Índice sheet -> {table id: title}."""
    out: dict[str, str] = {}
    for row in rows:
        cells = [_text(c) for c in row if _text(c)]
        if len(cells) >= 2 and _TABLE_ID.match(cells[0]):
            out[cells[0]] = cells[1]
    return out


def _sheet_entry(name: str, rows: list[tuple[Any, ...]], fallback_title: str | None) -> dict[str, Any]:
    title = ""
    number = ""
    header_at: int | None = None
    for i, row in enumerate(rows):
        cells = [_text(c) for c in row]
        nonempty = [c for c in cells if c]
        if not nonempty:
            continue
        if _TITLE_LABEL.match(nonempty[0]) and len(nonempty) > 1 and not title:
            title = nonempty[1]
        elif _NUMBER_LABEL.match(nonempty[0]) and len(nonempty) > 1 and not number:
            number = nonempty[1]
        elif nonempty[0].lower().startswith("índice") and len(nonempty) > 1 and header_at is None:
            header_at = i
    title = (title or fallback_title or "")[:_MAX_TEXT * 2]

    geo = ""
    columns: list[str] = []
    if header_at is not None:
        header = [_text(c) for c in rows[header_at] if _text(c)]
        geo = header[1] if len(header) > 1 else ""
        seen: set[str] = set()
        for j, row in enumerate(rows[header_at : header_at + 4]):
            if j and any(_is_number(c) for c in row):
                break
            for k, cell in enumerate(row):
                value = _text(cell)
                if j == 0 and k < 2:
                    continue  # "Índice" and the geography header
                if len(value) > 1 and not _is_number(cell) and value not in seen:
                    seen.add(value)
                    columns.append(value[:_MAX_TEXT])
    entry: dict[str, Any] = {"hoja": name, "titulo": title}
    if number and number != name:
        entry["tabla"] = number
    levels = detect_levels(title, geo)
    if levels:
        entry["niveles"] = levels
    if columns:
        entry["columnas"] = columns[:_MAX_COLUMNS]
    return entry


def extract_workbook_index(raw: bytes) -> list[dict[str, Any]]:
    """Per-sheet index of one tabulado workbook (sheet, title, levels, columns)."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        heads: dict[str, list[tuple[Any, ...]]] = {}
        for ws in wb.worksheets:
            heads[ws.title] = list(ws.iter_rows(max_row=_HEAD_ROWS, values_only=True))
        titles: dict[str, str] = {}
        for name, rows in heads.items():
            if strip_accents(name).lower().strip() == "indice":
                titles = _index_titles(rows)
        return [
            _sheet_entry(name, rows, titles.get(name.strip()))
            for name, rows in heads.items()
            if strip_accents(name).lower().strip() != "indice"
        ]
    finally:
        wb.close()


def file_entry(resource: dict[str, Any], raw: bytes, today: str) -> dict[str, Any]:
    """Index record of one downloaded tabulado."""
    sheets = extract_workbook_index(raw)
    levels = sorted({lv for s in sheets for lv in s.get("niveles", [])}, key=[l for _, l in _LEVELS].index)
    entry: dict[str, Any] = {
        "url": resource["url"],
        "label": resource["label"],
        "tema": resource.get("tema"),
        "formato": resource["format"],
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "extraido": today,
        "niveles": levels,
        "hojas": sheets,
    }
    return entry


async def build_index(max_mb: float = DEFAULT_MAX_MB) -> dict[str, Any]:
    """Read every tabulado XLSX listed on /resultados-censo/ into an index dict."""
    from helpers import censo_client
    from helpers.csv_reader import download_bytes

    limit = int(max_mb * 1024 * 1024)
    resources = await censo_client.fetch_live_resources()
    targets = [r for r in resources if r.get("tipo") == "tabulado" and r["format"] == "XLSX"]
    # "Serie histórica" sits outside the tema tabs but is a workbook of tables too.
    targets += [
        r
        for r in resources
        if r.get("tipo") != "tabulado"
        and r["format"] == "XLSX"
        and "serie" in r["label"].lower()
        and "hist" in r["label"].lower()
    ]
    today = datetime.now(UTC).date().isoformat()
    files: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for resource in targets:
        raw, truncated = await download_bytes(resource["url"], max_bytes=limit)
        if truncated:
            logger.warning("Skipping %s: larger than %.0f MB", resource["url"], max_mb)
            skipped.append({"url": resource["url"], "label": resource["label"], "motivo": f"supera {max_mb:g} MB"})
            continue
        try:
            files.append(file_entry(resource, raw, today))
        except Exception as exc:  # a corrupt workbook must not sink the whole build
            logger.warning("Skipping %s: unreadable workbook (%s)", resource["url"], exc)
            skipped.append({"url": resource["url"], "label": resource["label"], "motivo": f"ilegible: {exc}"})
            continue
        logger.info("Indexed %s (%d sheets)", resource["label"], len(files[-1]["hojas"]))
    if not files:
        raise RuntimeError("No tabulado workbook could be indexed; not writing an empty index")
    return {
        "version": 1,
        "generado": today,
        "fuente": censo_client.RESULTADOS_URL,
        "max_mb": max_mb,
        "omitidos": skipped,
        "archivos": files,
    }


def write_index(index: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=INDEX_PATH, help="JSON file to write")
    parser.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB, help="skip workbooks above this size")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    index = asyncio.run(build_index(args.max_mb))
    write_index(index, args.out)
    sheets = sum(len(f["hojas"]) for f in index["archivos"])
    print(
        f"{len(index['archivos'])} workbooks, {sheets} tables, "
        f"{len(index['omitidos'])} skipped -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

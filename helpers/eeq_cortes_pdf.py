"""Turn EEQ's scheduled power-cut PDFs into rows: time block × substation ×
sectors. See docs/RESEARCH.md § Trigésimo tercera pasada.

The PDFs are designed slides, not tables: pypdf's plain text loses which
substation goes with which sectors, so this works from positioned text
chunks (pypdf's `visitor_text`). Layout, confirmed on all 26 PDFs in the
archive (Oct 2023 - Dec 2024):

- sectors: the middle column (x ≈ 440 on a 2000-wide page, font < 20pt),
  one row of the grid per substation, wrapped over several lines;
- substation labels: the left column (x < 400), vertically centered on
  their row — font 23 in 2024, the same 17pt as the sectors in 2023;
- time block: from April 2024 on, one per page in large type in the header
  ("07:30 - 10:30", "10h30 - 14h00", "De 18:00 a 19:00", several joined by
  "/"); in the Oct-Nov 2023 layout, a third far-left column ("08:00" / "a" /
  "10:00") spanning several substation rows;
- date: the remaining large header text ("Viernes 04 al domingo 06 / de
  octubre de 2024"), kept as published — it is a range more often than not.

Rows are separated by a blank line (twice the line pitch); some pages are
a compact grid with no blank lines, so rows are also split between
consecutive substation labels at the midpoint between their centers.
"""

from __future__ import annotations

import io
import re
from itertools import pairwise
from typing import Any

from pypdf import PdfReader

_TIME_RE = re.compile(
    r"(\d{1,2})\s*[:h]\s*(\d{2})\s*(?:[-\u2010\u2013\u2014]|a)\s*(\d{1,2})\s*[:h]\s*(\d{2})"
)
_TIME_TOKEN_RE = re.compile(r"^(\d{1,2}\s*[:h]\s*\d{2}|a|-)$")
_HEADER_SKIP = (
    "Programaci",
    "cortes del servicio",
    "de energ",
    "RECUERDA",
    "DE ENERG",
    "Sectores",
    "Ministerio",
    "Energía y Minas",
)
_LABEL_NOISE = ("IMPORTANTE", "NOTA", "Estos horarios", "Ministerio", "Hora")
_BANNER_RE = re.compile(r"SECTOR|INDUSTRI|^AV\d+$")
_BIG_FONT = 30.0
_BODY_FONT = 20.0
_LEFT_COLUMN_X = 400.0
_TIME_COLUMN_X = 200.0
_SECTOR_MAX_X = 1800.0

Chunk = tuple[float, float, float, str]  # x, y, font size, text


def _chunks(page: Any) -> list[Chunk]:
    out: list[Chunk] = []

    def visit(
        text: str, cm: list[float], tm: list[float], _font: Any, size: float
    ) -> None:
        text = text.strip()
        if text:
            out.append(
                (
                    tm[4] * cm[0] + cm[4],
                    tm[5] * cm[3] + cm[5],
                    abs(size * tm[0] * cm[0]),
                    text,
                )
            )

    page.extract_text(visitor_text=visit)
    return out


def parse_horario(text: str) -> list[str]:
    """`"04:00 - 08:00 / 18:00 - 19:00"` → `["04:00-08:00", "18:00-19:00"]`."""
    return [
        f"{int(a):02d}:{b}-{int(c):02d}:{d}" for a, b, c, d in _TIME_RE.findall(text)
    ]


def _join(chunks: list[Chunk]) -> str:
    return re.sub(r"\s+", " ", " ".join(c[3] for c in chunks)).strip()


def _merge_labels(chunks: list[Chunk]) -> list[tuple[str, float]]:
    """Join labels wrapped over several lines ("SANTA" / "ROSA") into
    (text, y_center), top to bottom."""
    groups: list[list[Chunk]] = []
    for c in sorted(chunks, key=lambda c: -c[1]):
        if groups and groups[-1][-1][1] - c[1] < c[2] * 1.4:
            groups[-1].append(c)
        else:
            groups.append([c])
    return [(_join(g), (g[0][1] + g[-1][1]) / 2) for g in groups]


def _band(labels: list[tuple[str, float]], y: float) -> int:
    """Index of the label whose midpoint band contains y (labels top-down)."""
    return sum(1 for a, b in pairwise(labels) if y < (a[1] + b[1]) / 2)


def _time_labels(tokens: list[Chunk]) -> list[tuple[list[str], float]]:
    """Group the 2023 layout's stacked "08:00" / "a" / "10:00" tokens into
    (intervals, y_center), top to bottom. Grouped by sequence, not spacing:
    the stack's line pitch varies between pages."""
    labels: list[tuple[list[str], float]] = []
    pending: list[Chunk] = []
    for c in sorted(tokens, key=lambda c: -c[1]):
        pending.append(c)
        horario = parse_horario(_join(pending))
        if horario:
            labels.append((horario, (pending[0][1] + pending[-1][1]) / 2))
            pending = []
    return labels


def parse_page(page: Any) -> list[dict[str, Any]]:
    chunks = _chunks(page)

    # The "Sectores" column header marks where the sectors column starts;
    # it moved (x ≈ 330 in Nov 2023, ≈ 440 later), so read it per page.
    header = next((c for c in chunks if c[3].startswith("Sectores")), None)
    column_x = header[0] - 20 if header else _LEFT_COLUMN_X
    big = [c for c in chunks if c[2] >= _BIG_FONT]
    # dict.fromkeys: some pages print the same interval twice.
    header_horario = list(dict.fromkeys(h for c in big for h in parse_horario(c[3])))

    # Pages for industrial customers carry a "SECTOR INDUSTRIAL" banner in
    # the same large type as the date; keep it as a flag, not in the date.
    # They also repeat the date around the banner, hence the dedupe.
    industrial = any("INDUSTRI" in c[3] for c in big)
    fecha_parts = [
        c[3]
        for c in sorted(big, key=lambda c: -c[1])
        if not parse_horario(c[3])
        and not c[3].startswith(_HEADER_SKIP)
        and not _BANNER_RE.search(c[3])
        and not (c[0] < _TIME_COLUMN_X and _TIME_TOKEN_RE.match(c[3]))
    ]
    fecha = re.sub(r"\s+", " ", " ".join(dict.fromkeys(fecha_parts))).strip()

    body = [c for c in chunks if c[2] < _BIG_FONT and not c[3].startswith(_HEADER_SKIP)]
    sectors = sorted(
        (c for c in body if c[2] < _BODY_FONT and column_x <= c[0] < _SECTOR_MAX_X),
        key=lambda c: -c[1],
    )
    if not sectors:
        return []
    gaps = [a[1] - b[1] for a, b in pairwise(sectors) if a[1] - b[1] > 5]
    pitch = min(gaps) if gaps else 21.0
    top, bottom = sectors[0][1], sectors[-1][1]

    # Left-column text outside the grid's vertical span is a footer or a
    # notice ("IMPORTANTE", ministry branding), never a substation.
    left = [
        c
        for c in body
        if c[0] < column_x
        and bottom - 2 * pitch <= c[1] <= top + pitch
        and not c[3].startswith(_LABEL_NOISE)
    ]
    # Taken from every chunk, not just `left`: the stacked times are 27-30pt,
    # straddling the header-size cutoff from page to page.
    time_tokens = [
        c
        for c in chunks
        if c[0] < _TIME_COLUMN_X
        and bottom - 2 * pitch <= c[1] <= top + pitch
        and _TIME_TOKEN_RE.match(c[3])
    ]
    label_chunks = [
        c for c in left if not (c[0] < _TIME_COLUMN_X and _TIME_TOKEN_RE.match(c[3]))
    ]
    labels = _merge_labels(label_chunks)
    time_labels = _time_labels(time_tokens)

    rows: list[list[Chunk]] = [[sectors[0]]]
    for a, b in pairwise(sectors):
        if a[1] - b[1] > pitch * 1.5:
            rows.append([])
        rows[-1].append(b)

    out: list[dict[str, Any]] = []
    for row in rows:
        mine = [
            lab for lab in labels if row[-1][1] - pitch <= lab[1] <= row[0][1] + pitch
        ]
        if len(mine) <= 1:
            parts = [(mine[0][0] if mine else None, row)]
        else:
            split: list[list[Chunk]] = [[] for _ in mine]
            for c in row:
                split[_band(mine, c[1])].append(c)
            parts = [(m[0], p) for m, p in zip(mine, split) if p]
        for name, lines in parts:
            horario = header_horario
            if not horario and time_labels:
                center = (lines[0][1] + lines[-1][1]) / 2
                horario = time_labels[_band(time_labels, center)][0]
            out.append(
                {
                    "fecha_texto": fecha,
                    "sector_industrial": industrial,
                    "horario": horario,
                    "subestacion": name,
                    "sectores": _join(lines),
                }
            )
    return out


def parse_pdf(raw: bytes) -> dict[str, Any]:
    reader = PdfReader(io.BytesIO(raw))
    filas: list[dict[str, Any]] = []
    for n, page in enumerate(reader.pages, 1):
        for fila in parse_page(page):
            filas.append({"pagina": n, **fila})
    return {
        "paginas": len(reader.pages),
        "filas": filas,
        "filas_sin_subestacion": sum(1 for f in filas if not f["subestacion"]),
        "filas_sin_horario": sum(1 for f in filas if not f["horario"]),
    }

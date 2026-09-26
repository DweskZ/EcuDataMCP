"""Turn Centrosur's scheduled power-cut PDFs into rows: time block ×
province × canton × zone × sectors. See docs/RESEARCH.md § Trigésimo
cuarta pasada.

The archive is small (8 files, 3 of them identical copies) but not
uniform. What each kind needs, confirmed on every file 2026-09-25:

- **Tables (Oct 2023, 3 files):** columns PROVINCIA / CANTÓN / ÁREA or ZONA
  DE CORTE / SECTORES, one time block per file in the header ("08:00 ‐
  12:00", "De 15:00 ‐ 18:00"). Two of them are landscape pages stored as
  portrait + `/Rotate 90`, so chunk coordinates are rotated back to reading
  orientation. Province and canton are sometimes merged cells spanning
  several rows, printed once.
- **Infographic (Apr 2024, 1 file uploaded 3 times):** a single very tall
  page with several time sections stacked vertically, each with its own
  CANTÓN / ZONA DE CORTE / SECTORES table.
- **EEQ's own PDF (`DESCONEXION-30-31-01-1`):** Quito's substations,
  uploaded to Centrosur's media library by mistake; parsed with the EEQ
  parser and flagged.
- **Image-only (Sep 2024, 22 MB):** no text layer at all; would need OCR,
  which this project doesn't do. Reported, not parsed.

Common approach: text on the right of the table whose lines are long and
comma-separated is sectors; everything left of it is row labels. Rows are
the sector runs separated by a blank line, or split between consecutive
zone labels when the grid is compact. Province/canton come from the
labels, matched against the national canton list; a label that is only a
province or canton name (a merged cell) applies to the rows it is
centered on.
"""

from __future__ import annotations

import io
import re
from functools import cache
from itertools import pairwise
from typing import Any

from pypdf import PdfReader

from helpers.eeq_cortes_pdf import parse_horario
from helpers.eeq_cortes_pdf import parse_pdf as parse_eeq_pdf
from helpers.geo_data import list_cantones, list_provincias
from helpers.text_utils import strip_accents as _strip

Chunk = tuple[float, float, float, str]  # x, y (up), font size, text

_TIME_FONT_MIN = 18.0
_SECTOR_MIN_LEN = 30
_HEADER_RE = re.compile(
    r"(PROVINCIA|CANT[OÓ]N).*SECTORES|SECTORES.*SUBESTACIONES", re.IGNORECASE
)
_NOISE_RE = re.compile(
    r"^(Programaci|cortes del servicio|de energ|[ÁA]rea de concesi|Azuay, Ca|Fecha|"
    r"PROVINCIA|CANT[OÓ]N ZONA)",
    re.IGNORECASE,
)

# The PDFs name some cantons by their seat, not the canton.
_CANTON_ALIASES = {
    "MENDEZ": "Santiago",
    "LIMON": "Limon Indanza",
    "MACAS": "Morona",
}


@cache
def _places() -> tuple[dict[str, str], dict[str, str]]:
    """Accent-free uppercase names → display name, for the concession's
    provinces (Azuay, Cañar, Morona Santiago) and their cantons."""
    concession = {"01", "03", "14"}
    provincias = {
        _strip(p["nombre"]).upper(): p["nombre"]
        for p in list_provincias()
        if p["codigo"] in concession
    }
    cantones = {
        _strip(c["nombre"]).upper(): c["nombre"]
        for c in list_cantones()
        if c["provincia_codigo"] in concession
    }
    for alias, canton in _CANTON_ALIASES.items():
        cantones[alias] = canton
    return provincias, cantones


@cache
def _provincia_de() -> dict[str, str]:
    return {c["nombre"]: c["provincia"] for c in list_cantones()}


def _chunks(page: Any) -> list[Chunk]:
    """Positioned text in reading orientation, including pages stored
    rotated (text matrix [0, s, -s, 0, e, f] under /Rotate 90)."""
    out: list[Chunk] = []

    def visit(
        text: str, cm: list[float], tm: list[float], _font: Any, size: float
    ) -> None:
        text = text.strip()
        if not text:
            return
        if abs(tm[0]) < 1e-6 and tm[1] > 0:
            out.append((tm[5], -tm[4], abs(tm[1] * size), text))
        else:
            x = tm[4] * cm[0] + cm[4]
            y = tm[5] * cm[3] + cm[5]
            out.append((x, y, abs(tm[0] * size * cm[0]), text))

    page.extract_text(visitor_text=visit)
    return out


def _assemble(chunks: list[Chunk]) -> list[Chunk]:
    """Merge word-level chunks on the same baseline into line segments.
    Two of the tables emit one chunk per word; columns stay apart because
    the gap between them is far wider than a space. Widths are estimated
    (pypdf's visitor gives no glyph widths): ~0.55 em per character."""
    out: list[Chunk] = []
    for c in sorted(chunks, key=lambda c: (-round(c[1]), c[0])):
        if out:
            x, y, size, text = out[-1]
            end = x + len(text) * 0.55 * size
            if abs(y - c[1]) < 1.5 and c[0] > x and c[0] - end < 1.5 * max(size, c[2]):
                out[-1] = (x, y, max(size, c[2]), f"{text} {c[3]}")
                continue
        out.append(c)
    return out


def _cut(lines: list[Chunk], upper: float, lower: float) -> float:
    """Where one row ends and the next starts between two zone-label
    centers: the widest gap between sector lines in that range (rows are
    only slightly farther apart than wrapped lines), else the midpoint."""
    between = [c[1] for c in lines if lower < c[1] < upper]
    ys = [upper, *between, lower]
    best = max(pairwise(ys), key=lambda ab: ab[0] - ab[1])
    return (best[0] + best[1]) / 2 if between else (upper + lower) / 2


def _join(chunks: list[Chunk]) -> str:
    return re.sub(r"\s+", " ", " ".join(c[3] for c in chunks)).strip()


def _split_place(label: str) -> tuple[str | None, str | None, str]:
    """ "AZUAY CUENCA GAPAL" → ("Azuay", "Cuenca", "GAPAL"). Longest names
    first so "MORONA SANTIAGO" wins over the canton "Morona"."""
    provincias, cantones = _places()
    words = label.split()
    provincia = canton = None
    for table, slot in ((provincias, "p"), (cantones, "c")):
        for n in range(min(3, len(words)), 0, -1):
            key = _strip(" ".join(words[:n])).upper()
            if key in table:
                if slot == "p":
                    provincia = table[key]
                else:
                    canton = table[key]
                words = words[n:]
                break
    return provincia, canton, " ".join(words)


def _parse_section(
    chunks: list[Chunk], horario: list[str], fecha: str
) -> list[dict[str, Any]]:
    long_lines = sorted(
        c[0] for c in chunks if "," in c[3] and len(c[3]) >= _SECTOR_MIN_LEN
    )
    if not long_lines:
        return []

    # Left edge of the sectors column: where most long comma-separated
    # lines start, not the leftmost one — a zone label can contain a comma
    # too. Buckets of 20 pt absorb centered text's jitter.
    buckets: dict[int, int] = {}
    for x in long_lines:
        buckets[int(x // 20)] = buckets.get(int(x // 20), 0) + 1
    mode = max(buckets, key=lambda b: (buckets[b], -b))
    split_x = min(x for x in long_lines if x >= (mode - 1) * 20) - 15
    sectors = sorted((c for c in chunks if c[0] >= split_x), key=lambda c: -c[1])
    labels = [c for c in chunks if c[0] < split_x]
    if not sectors:
        return []

    gaps = [a[1] - b[1] for a, b in pairwise(sectors) if a[1] - b[1] > 2]
    pitch = min(gaps) if gaps else 9.0
    provincias, cantones = _places()

    # Labels that are only a province or canton name are merged cells.
    def only_place(c: Chunk) -> bool:
        key = _strip(c[3]).upper()
        return key in provincias or key in cantones

    span_labels = [c for c in labels if only_place(c)]
    left_x = min((c[0] for c in labels), default=0.0)
    row_labels = [c for c in labels if not only_place(c)]

    rows: list[list[Chunk]] = [[sectors[0]]]
    for a, b in pairwise(sectors):
        if a[1] - b[1] > pitch * 1.6:
            rows.append([])
        rows[-1].append(b)

    # Each label belongs to exactly one row: the one whose vertical span
    # contains it, else the nearest (zone labels are centered on tall rows).
    def distance(row: list[Chunk], y: float) -> float:
        top, bottom = row[0][1], row[-1][1]
        return 0.0 if bottom <= y <= top else min(abs(y - top), abs(y - bottom))

    by_row: list[list[Chunk]] = [[] for _ in rows]
    for c in row_labels:
        by_row[min(range(len(rows)), key=lambda i: distance(rows[i], c[1]))].append(c)

    # Merged province/canton cells are printed once, vertically centered on
    # the rows they span; spans are contiguous, so each boundary follows
    # from the previous one: center = (top + bottom) / 2. Computed per
    # column, since province and canton merge independently.
    table_top = rows[0][0][1] + pitch
    columns: dict[int, list[Chunk]] = {}
    for c in span_labels:
        columns.setdefault(int(c[0] // 40), []).append(c)
    spans: list[tuple[float, float, Chunk]] = []  # top, bottom, label
    for col in columns.values():
        col.sort(key=lambda c: -c[1])
        start = table_top
        for i, c in enumerate(col):
            end = 2 * c[1] - start
            nxt = col[i + 1][1] if i + 1 < len(col) else None
            if end > c[1] or (nxt is not None and end <= nxt):
                end = (c[1] + nxt) / 2 if nxt is not None else float("-inf")
            spans.append((start, end, c))
            start = end

    def spanning(y: float) -> tuple[str | None, str | None, float | None]:
        provincia = canton = None
        canton_y = None
        for top, bottom, label in spans:
            if bottom < y <= top:
                key = _strip(label[3]).upper()
                if key in cantones and canton is None:
                    canton, canton_y = cantones[key], label[1]
                elif key in provincias:
                    provincia = provincia or provincias[key]
        return provincia, canton, canton_y

    out: list[dict[str, Any]] = []
    for row, row_own in zip(rows, by_row):
        mine = sorted(row_own, key=lambda c: -c[1])

        # Compact grid: several zone labels inside one gapless run of
        # sectors. Zone labels wrapped over lines sit closer than a row.
        groups: list[list[Chunk]] = []
        for c in mine:
            if groups and groups[-1][-1][1] - c[1] <= pitch * 1.2:
                groups[-1].append(c)
            else:
                groups.append([c])
        if len(groups) <= 1:
            parts = [(groups[0] if groups else [], row)]
        else:
            anchors = [(g[0][1] + g[-1][1]) / 2 for g in groups]
            cuts = [_cut(row, a, b) for a, b in pairwise(anchors)]
            split: list[list[Chunk]] = [[] for _ in groups]
            for c in row:
                split[sum(1 for cut in cuts if c[1] < cut)].append(c)
            parts = list(zip(groups, split))

        for group, lines in parts:
            if not lines:
                continue
            # Only labels starting in the leftmost label column carry a
            # province/canton prefix; in the zone column a leading place
            # name is part of the zone ("GUALACEO CENTRO").
            if group and group[0][0] <= left_x + 40:
                provincia, canton, zona = _split_place(_join(group))
            else:
                provincia, canton, zona = None, None, _join(group)
            span_provincia, span_canton, span_y = spanning(
                (lines[0][1] + lines[-1][1]) / 2
            )

            # A canton read from the row's own label is reliable; one taken
            # from a merged cell is an estimate that can be off by a row or
            # two at span boundaries (cells aren't always centered exactly,
            # and spans can cross pages). Flagged so callers can tell.
            # A canton cell level with this row's own lines is the row's own.
            inferido = (
                canton is None
                and span_canton is not None
                and not (lines[-1][1] - pitch <= span_y <= lines[0][1] + pitch)
            )
            canton = canton or span_canton

            # The canton decides the province when known: merged province
            # cells are the least reliable label on the page.
            if canton is not None:
                provincia = _provincia_de().get(canton, provincia)
            provincia = provincia or span_provincia
            out.append(
                {
                    "fecha_texto": fecha,
                    "horario": horario,
                    "provincia": provincia,
                    "canton": canton,
                    "canton_inferido": inferido,
                    "zona": zona or None,
                    "sectores": _join(lines),
                }
            )
    return out


def parse_page(page: Any) -> list[dict[str, Any]]:
    chunks = _assemble(_chunks(page))
    time_labels = sorted(
        (c for c in chunks if c[2] >= _TIME_FONT_MIN and parse_horario(c[3])),
        key=lambda c: -c[1],
    )
    header = next((c for c in chunks if _HEADER_RE.search(c[3])), None)
    fecha_chunks = [
        c
        for c in chunks
        if c[2] >= _TIME_FONT_MIN
        and not parse_horario(c[3])
        and not _NOISE_RE.match(c[3])
        and not re.fullmatch(r"(Programación|Azuay|De)", c[3])
        and (header is None or c[1] > header[1])
    ]
    fecha = _join(sorted(fecha_chunks, key=lambda c: (-round(c[1]), c[0])))
    fecha = re.sub(r"^Fecha:\s*", "", fecha)
    body = [
        c
        for c in chunks
        if c[2] < _TIME_FONT_MIN
        and not _NOISE_RE.match(c[3])
        and not _HEADER_RE.search(c[3])
        and (header is None or c[1] < header[1])
    ]

    # Several time sections stacked on one page (the Apr 2024 infographic):
    # each owns the body text below it, down to the next time label. The
    # time label sits level with its section's top, on the right.
    if len(time_labels) > 1:
        out = []
        for i, t in enumerate(time_labels):
            floor = time_labels[i + 1][1] if i + 1 < len(time_labels) else float("-inf")
            section = [
                c for c in chunks if c[2] < _TIME_FONT_MIN and floor < c[1] < t[1]
            ]
            section = [
                c
                for c in section
                if not _NOISE_RE.match(c[3]) and not _HEADER_RE.search(c[3])
            ]
            out.extend(_parse_section(section, parse_horario(t[3]), fecha))
        return out

    horario = parse_horario(time_labels[0][3]) if time_labels else []
    return _parse_section(body, horario, fecha)


def parse_pdf(raw: bytes) -> dict[str, Any]:
    reader = PdfReader(io.BytesIO(raw))
    first_text = reader.pages[0].extract_text() or "" if reader.pages else ""

    if "Subestaciones" in first_text:
        eeq = parse_eeq_pdf(raw)
        return {
            "paginas": eeq["paginas"],
            "formato": "eeq",
            "nota": (
                "Este PDF es de la Empresa Eléctrica Quito (subestaciones de "
                "Quito), publicado por error en el sitio de Centrosur."
            ),
            "filas": eeq["filas"],
            "filas_sin_horario": eeq["filas_sin_horario"],
        }

    if not any((p.extract_text() or "").strip() for p in reader.pages):
        return {
            "paginas": len(reader.pages),
            "formato": "imagen",
            "nota": (
                "El PDF no tiene capa de texto (solo imágenes escaneadas); "
                "extraer sus horarios requeriría OCR."
            ),
            "filas": [],
            "filas_sin_horario": 0,
        }

    filas: list[dict[str, Any]] = []
    for n, page in enumerate(reader.pages, 1):
        for fila in parse_page(page):
            filas.append({"pagina": n, **fila})

    # Tables spanning pages print the time block only on the first one.
    horario = next((f["horario"] for f in filas if f["horario"]), [])
    fecha = next((f["fecha_texto"] for f in filas if f["fecha_texto"]), "")
    for f in filas:
        f["horario"] = f["horario"] or horario
        f["fecha_texto"] = f["fecha_texto"] or fecha

    return {
        "paginas": len(reader.pages),
        "formato": "tabla",
        "nota": None,
        "filas": filas,
        "filas_sin_horario": sum(1 for f in filas if not f["horario"]),
    }

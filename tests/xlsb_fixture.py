"""A minimal .xlsb writer, for tests: no Python library writes the format.

Only what pyxlsb reads is written: the sheet list in workbook.bin, a shared
string table, and one worksheet part per sheet holding numbers and strings.
Records are BIFF12: a 1-2 byte id, a 7-bit varint length, then the payload.
"""

import io
import struct
import zipfile

_WORKBOOK, _SHEETS, _SHEETS_END, _SHEET = 0x0183, 0x018F, 0x0190, 0x019C
_SST, _SST_END, _SI = 0x019F, 0x01A0, 0x0013
_WORKSHEET, _WORKSHEET_END, _DIMENSION = 0x0181, 0x0182, 0x0194
_SHEETDATA, _SHEETDATA_END = 0x0191, 0x0192
_ROW, _FLOAT, _STRING = 0x0000, 0x0005, 0x0007


def _record(record_id: int, payload: bytes = b"") -> bytes:
    id_bytes = record_id.to_bytes(1 if record_id < 0x80 else 2, "little")
    length, varint = len(payload), bytearray()
    while True:
        low, length = length & 0x7F, length >> 7
        varint.append(low | (0x80 if length else 0))
        if not length:
            return id_bytes + bytes(varint) + payload


def _wide_string(text: str) -> bytes:
    return struct.pack("<I", len(text)) + text.encode("utf-16-le")


def _worksheet(rows: list[list], strings: list[str]) -> bytes:
    width = max((len(row) for row in rows), default=0)
    parts = [
        _record(_WORKSHEET),
        _record(_DIMENSION, struct.pack("<IIII", 0, max(len(rows) - 1, 0), 0, max(width - 1, 0))),
        _record(_SHEETDATA),
    ]
    for r, row in enumerate(rows):
        parts.append(_record(_ROW, struct.pack("<I", r)))
        for c, value in enumerate(row):
            if value is None:
                continue
            if isinstance(value, str):
                if value not in strings:
                    strings.append(value)
                payload = struct.pack("<I", strings.index(value))
                parts.append(_record(_STRING, struct.pack("<II", c, 0) + payload))
            else:
                parts.append(_record(_FLOAT, struct.pack("<IId", c, 0, float(value))))
    parts += [_record(_SHEETDATA_END), _record(_WORKSHEET_END)]
    return b"".join(parts)


def make_xlsb(sheets: dict[str, list[list]]) -> bytes:
    """An .xlsb workbook with one sheet per key, rows of str/number/None cells."""
    strings: list[str] = []
    sheet_parts = [_worksheet(rows, strings) for rows in sheets.values()]
    workbook = [_record(_WORKBOOK), _record(_SHEETS)]
    rels = []
    for i, name in enumerate(sheets, start=1):
        workbook.append(
            _record(_SHEET, struct.pack("<II", 0, i) + _wide_string(f"rId{i}") + _wide_string(name))
        )
        rels.append(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.bin"/>')
    workbook.append(_record(_SHEETS_END))
    table = [_record(_SST, struct.pack("<II", len(strings), len(strings)))]
    table += [_record(_SI, b"\x00" + _wide_string(text)) for text in strings]
    table.append(_record(_SST_END))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.bin", b"".join(workbook))
        zf.writestr(
            "xl/_rels/workbook.bin.rels", f"<Relationships>{''.join(rels)}</Relationships>"
        )
        zf.writestr("xl/sharedStrings.bin", b"".join(table))
        for i, part in enumerate(sheet_parts, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.bin", part)
    return buf.getvalue()

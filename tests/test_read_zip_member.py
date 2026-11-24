import io
import json
import re
import socket
import struct
import zipfile
import zlib

import httpx
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import csv_reader
from helpers.csv_reader import list_zip_contents, read_zip_member
from tools.read_zip_member import register_read_zip_member_tool

URL = "https://example.com/tabulados.zip"
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


def _make_zip(members: dict[str, bytes], method: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=method) as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _raw_zip(
    name: str,
    data: bytes,
    *,
    local_extra: bytes = b"",
    cd_extra: bytes = b"",
    flags: int = 0,
    method: int = 8,
    crc: int | None = None,
) -> bytes:
    """Hand-built single-member zip, for fields zipfile won't let us set."""
    payload = zlib.compress(data, 9)[2:-4] if method == 8 else data
    crc = zlib.crc32(data) if crc is None else crc
    name_b = name.encode()
    local = (
        struct.pack(
            "<4sHHHHHIIIHH",
            b"PK\x03\x04",
            20,
            flags,
            method,
            0,
            0,
            crc,
            len(payload),
            len(data),
            len(name_b),
            len(local_extra),
        )
        + name_b
        + local_extra
        + payload
    )
    cd = (
        struct.pack(
            "<4sHHHHHHIIIHHHHHII",
            b"PK\x01\x02",
            20,
            20,
            flags,
            method,
            0,
            0,
            crc,
            len(payload),
            len(data),
            len(name_b),
            len(cd_extra),
            0,
            0,
            0,
            0,
            0,
        )
        + name_b
        + cd_extra
    )
    eocd = struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, 1, 1, len(cd), len(local), 0)
    return local + cd + eocd


def _serve(httpx_mock, blob: bytes, *, full_body: bool = False, shift: int = 0) -> None:
    """Answer Range requests from `blob`; optionally misbehave like real servers."""
    total = len(blob)

    def callback(request: httpx.Request) -> httpx.Response:
        if full_body:
            return httpx.Response(200, content=blob)
        first, last = _RANGE_RE.fullmatch(request.headers["Range"]).groups()
        if first == "":
            start, end = max(total - int(last), 0), total - 1
        else:
            start, end = int(first), min(int(last), total - 1)
            start += shift  # only explicit ranges, so the listing still works
        return httpx.Response(
            206,
            content=blob[start : end + 1],
            headers={"Content-Range": f"bytes {start}-{end}/{total}"},
        )

    httpx_mock.add_callback(callback, url=URL, is_reusable=True)


async def test_reads_a_deflate_csv_member(httpx_mock):
    csv_body = b"provincia,valor\nAzuay,1\nCarchi,2\n"
    _serve(httpx_mock, _make_zip({"T/INDICE.csv": b"x\n1\n", "T/T1_i1.csv": csv_body}))

    result = await read_zip_member(URL, "T/T1_i1.csv")

    assert result["headers"] == ["provincia", "valor"]
    assert result["rows"] == [["Azuay", "1"], ["Carchi", "2"]]
    assert result["member_name"] == "T/T1_i1.csv"
    assert result["format"] == "csv"
    assert result["uncompressed_size"] == len(csv_body)
    assert result["truncated"] is False


async def test_reads_a_stored_member(httpx_mock):
    _serve(httpx_mock, _make_zip({"a.tsv": b"x\ty\n1\t2\n"}, method=zipfile.ZIP_STORED))

    result = await read_zip_member(URL, "a.tsv")

    assert result["headers"] == ["x", "y"]
    assert result["rows"] == [["1", "2"]]
    assert result["compressed_size"] == result["uncompressed_size"]


async def test_decodes_a_cp1252_csv(httpx_mock):
    body = "cantón;año\nCañar;2024\n".encode("cp1252")
    _serve(httpx_mock, _make_zip({"datos.csv": body}))

    result = await read_zip_member(URL, "datos.csv")

    assert result["headers"] == ["cantón", "año"]
    assert result["rows"] == [["Cañar", "2024"]]


async def test_reads_an_xlsx_member(httpx_mock):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["indicador", "valor"])
    ws.append(["DCI", 20.1])
    xbuf = io.BytesIO()
    wb.save(xbuf)
    _serve(httpx_mock, _make_zip({"libro.xlsx": xbuf.getvalue()}))

    result = await read_zip_member(URL, "libro.xlsx")

    assert result["format"] == "xlsx"
    assert result["headers"] == ["indicador", "valor"]
    assert result["rows"] == [["DCI", "20.1"]]


async def test_matches_case_insensitively_and_by_basename(httpx_mock):
    _serve(httpx_mock, _make_zip({"Carpeta/T1_I1.CSV": b"a\n1\n"}))

    by_case = await read_zip_member(URL, "carpeta/t1_i1.csv")
    by_basename = await read_zip_member(URL, "T1_I1.CSV")

    assert by_case["member_name"] == by_basename["member_name"] == "Carpeta/T1_I1.CSV"


async def test_not_found_suggests_close_names(httpx_mock):
    _serve(httpx_mock, _make_zip({"T1_i1.csv": b"a\n1\n", "T1_i2.csv": b"a\n1\n"}))

    with pytest.raises(ValueError, match=r"T1_i1\.csv"):
        await read_zip_member(URL, "T1_i9.csv")


async def test_rejects_a_directory_member(httpx_mock):
    _serve(httpx_mock, _make_zip({"carpeta/": b"", "carpeta/a.csv": b"a\n1\n"}))

    with pytest.raises(ValueError, match="carpeta"):
        await read_zip_member(URL, "carpeta/")


async def test_rejects_an_encrypted_member(httpx_mock):
    _serve(httpx_mock, _raw_zip("a.csv", b"a\n1\n", flags=0x1))

    with pytest.raises(ValueError, match="cifrado"):
        await read_zip_member(URL, "a.csv")


async def test_rejects_an_unsupported_compression_method(httpx_mock):
    _serve(httpx_mock, _raw_zip("a.csv", b"a\n1\n", method=12))

    with pytest.raises(ValueError, match="compresión no soportado"):
        await read_zip_member(URL, "a.csv")


async def test_rejects_an_oversized_member(httpx_mock, monkeypatch):
    monkeypatch.setattr(csv_reader, "MAX_DOWNLOAD_BYTES", 8)
    _serve(
        httpx_mock,
        _make_zip({"a.csv": b"a,b\n" + b"1,2\n" * 50}, method=zipfile.ZIP_STORED),
    )

    with pytest.raises(ValueError, match="límite"):
        await read_zip_member(URL, "a.csv")


async def test_rejects_a_200_instead_of_206(httpx_mock):
    _serve(httpx_mock, _make_zip({"a.csv": b"a\n1\n"}), full_body=True)

    with pytest.raises(ValueError, match="Range"):
        await read_zip_member(URL, "a.csv")


async def test_rejects_a_mismatched_content_range_start(httpx_mock):
    _serve(httpx_mock, _make_zip({"a.csv": b"a\n1\n"}), shift=1)

    with pytest.raises(ValueError, match="Range"):
        await read_zip_member(URL, "a.csv")


async def test_rejects_a_crc_mismatch(httpx_mock):
    _serve(httpx_mock, _raw_zip("a.csv", b"a\n1\n", crc=0xDEADBEEF))

    with pytest.raises(ValueError, match="corrupto"):
        await read_zip_member(URL, "a.csv")


async def test_uses_the_local_extra_field_length(httpx_mock):
    # Writers such as Info-ZIP put a timestamp extra field only in the local
    # header; the data offset must come from the local lengths.
    local_extra = struct.pack("<HHB", 0x5455, 1, 0) + b"\x00" * 40
    _serve(httpx_mock, _raw_zip("a.csv", b"col\nvalor\n", local_extra=local_extra))

    result = await read_zip_member(URL, "a.csv")

    assert result["rows"] == [["valor"]]


async def test_list_zip_contents_output_is_unchanged(httpx_mock):
    _serve(httpx_mock, _make_zip({"a.csv": b"a\n1\n", "d/": b""}))

    result = await list_zip_contents(URL)

    assert set(result) == {"url", "total_size_bytes", "total_entries", "members"}
    for member in result["members"]:
        assert set(member) == {
            "name",
            "is_dir",
            "compressed_size",
            "uncompressed_size",
            "compression",
        }


async def test_tool_paginates_with_rows_and_offset(httpx_mock):
    body = b"n\n" + b"".join(f"{i}\n".encode() for i in range(10))
    _serve(httpx_mock, _make_zip({"serie.csv": body}))
    server = MCPServer("test")
    register_read_zip_member_tool(server)

    result = await server.call_tool(
        "read_zip_member",
        {"url": URL, "member": "serie.csv", "rows": 3, "offset": 4, "format": "json"},
    )

    payload = json.loads(result.content[0].text)
    assert payload["rows"] == [["4"], ["5"], ["6"]]
    assert payload["truncated"] is True


async def test_tool_maps_value_errors_to_tool_errors(httpx_mock):
    _serve(httpx_mock, _make_zip({"a.csv": b"a\n1\n"}))
    server = MCPServer("test")
    register_read_zip_member_tool(server)

    with pytest.raises(ToolError, match="list_zip_contents"):
        await server.call_tool("read_zip_member", {"url": URL, "member": "zzz.pdf"})


# -- report tables (INEC tabulados) -------------------------------------------

_TABULADO = (
    "Tabla N°:,1,,,,,,,,,,,\n"
    "Indicador/variable:,Porcentaje de hogares,,,,,,,,,,,\n"
    "Fuente:,ENDI 2025 - 2026,,,,,,,,,,,\n"
    ",,,,,,,,,,,,\n"
    "Desagregación,,Indicador,Error,Inferior,Superior,,,,,,,\n"
    '"Nacional *,Nacional,24.8,0.9,23.1,26.6,,,,",,,\n'
    "Provincia,Azuay,10.2,1.9,7.0,14.8,,,,,,,\n"
    ",Bolívar,14.2,1.8,11.1,18.1,,,,,,,\n"
).encode("cp1252")


async def test_detects_the_header_below_a_title_block(httpx_mock):
    _serve(httpx_mock, _make_zip({"T1_i1.csv": _TABULADO}))

    result = await read_zip_member(URL, "T1_i1.csv")

    assert result["header_row"] == 4
    assert result["headers"] == [
        "Desagregación",
        "",
        "Indicador",
        "Error",
        "Inferior",
        "Superior",
    ]
    assert result["preamble"][0] == "Tabla N°: | 1"
    assert result["rows"][0] == [
        "Nacional *",
        "Nacional",
        "24.8",
        "0.9",
        "23.1",
        "26.6",
    ]
    assert result["rows"][2] == ["", "Bolívar", "14.2", "1.8", "11.1", "18.1"]
    assert result["dropped_empty_columns"] > 0


async def test_skip_rows_zero_keeps_the_first_row(httpx_mock):
    _serve(httpx_mock, _make_zip({"T1_i1.csv": _TABULADO}))

    result = await read_zip_member(URL, "T1_i1.csv", skip_rows=0)

    assert result["header_row"] == 0
    assert result["headers"][:2] == ["Tabla N°:", "1"]


async def test_a_plain_csv_is_left_alone(httpx_mock):
    _serve(httpx_mock, _make_zip({"a.csv": b"x,y,z\n1,,3\n"}))

    result = await read_zip_member(URL, "a.csv")

    assert result["header_row"] == 0
    assert result["headers"] == ["x", "y", "z"]
    assert result["rows"] == [["1", "", "3"]]
    assert result["preamble"] == []


async def test_a_quoted_title_with_one_comma_is_not_split(httpx_mock):
    body = b'"Hogares con menores de 5, por area"\nx,y\n1,2\n'
    _serve(httpx_mock, _make_zip({"a.csv": body}))

    result = await read_zip_member(URL, "a.csv", skip_rows=1)

    assert result["preamble"] == ["Hogares con menores de 5, por area"]


# -- ZIP64 ------------------------------------------------------------------


async def test_reads_members_with_zip64_extra_fields(httpx_mock, monkeypatch):
    # A tiny ZIP64_LIMIT makes zipfile write ZIP64 sentinels and extra fields
    # (and ZIP64 end records) exactly as it does past 4 GB.
    with monkeypatch.context() as patch:
        patch.setattr(zipfile, "ZIP64_LIMIT", 8)
        blob = _make_zip({"a.csv": b"x,y\n1,2\n", "b.csv": b"n\n" + b"7\n" * 20})
    _serve(httpx_mock, blob)

    listing = await list_zip_contents(URL)
    result = await read_zip_member(URL, "b.csv")

    sizes = {m["name"]: m["uncompressed_size"] for m in listing["members"]}
    assert sizes == {"a.csv": 8, "b.csv": 42}
    assert result["rows"][0] == ["7"]


def _zip64_eocd_zip(name: str, data: bytes) -> bytes:
    """Single stored member whose classic EOCD holds only ZIP64 sentinels."""
    name_b = name.encode()
    crc = zlib.crc32(data)
    local = (
        struct.pack(
            "<4sHHHHHIIIHH",
            b"PK\x03\x04",
            45,
            0,
            0,
            0,
            0,
            crc,
            len(data),
            len(data),
            len(name_b),
            0,
        )
        + name_b
        + data
    )
    cd = (
        struct.pack(
            "<4sHHHHHHIIIHHHHHII",
            b"PK\x01\x02",
            45,
            45,
            0,
            0,
            0,
            0,
            crc,
            len(data),
            len(data),
            len(name_b),
            0,
            0,
            0,
            0,
            0,
            0,
        )
        + name_b
    )
    cd_offset = len(local)
    record_offset = cd_offset + len(cd)
    record = struct.pack(
        "<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, 0, 0, 1, 1, len(cd), cd_offset
    )
    locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, record_offset, 1)
    eocd = struct.pack(
        "<4sHHHHIIH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0
    )
    return local + cd + record + locator + eocd


async def test_reads_the_zip64_end_of_central_directory(httpx_mock):
    _serve(httpx_mock, _zip64_eocd_zip("datos.csv", b"a,b\n1,2\n"))

    listing = await list_zip_contents(URL)
    result = await read_zip_member(URL, "datos.csv")

    assert listing["total_entries"] == 1
    assert result["rows"] == [["1", "2"]]


async def test_fetches_a_zip64_record_outside_the_tail(httpx_mock, monkeypatch):
    # The locator (20 B) and EOCD (22 B) fit the tail; the 56-byte ZIP64
    # record before them does not, forcing its own Range request.
    monkeypatch.setattr(csv_reader, "_EOCD_TAIL_BYTES", 42)
    _serve(httpx_mock, _zip64_eocd_zip("datos.csv", b"a,b\n1,2\n"))

    result = await read_zip_member(URL, "datos.csv")

    assert result["rows"] == [["1", "2"]]


def _workbook(sheets: dict[str, list[list]]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_SIPA_LIKE = {
    "ÍNDICE": [["Contenido"], ["Piladoras"]],
    "Histórico Piladoras 12-25": [
        ["Año", "Mes", "Producto", "Precio"],
        [2026, "Octubre", "Arroz Pilado Natural Grano Largo", 44.5],
    ],
}


async def test_reads_a_named_sheet_and_lists_all_sheets(httpx_mock):
    _serve(httpx_mock, _make_zip({"libro.xlsx": _workbook(_SIPA_LIKE)}))

    result = await read_zip_member(URL, "libro.xlsx", sheet="histórico piladoras 12-25")

    assert result["sheet"] == "Histórico Piladoras 12-25"
    assert result["sheets"] == ["ÍNDICE", "Histórico Piladoras 12-25"]
    assert result["headers"] == ["Año", "Mes", "Producto", "Precio"]
    assert result["rows"] == [["2026", "Octubre", "Arroz Pilado Natural Grano Largo", "44.5"]]


async def test_reads_a_sheet_by_number(httpx_mock):
    _serve(httpx_mock, _make_zip({"libro.xlsx": _workbook(_SIPA_LIKE)}))

    result = await read_zip_member(URL, "libro.xlsx", sheet="2")

    assert result["sheet"] == "Histórico Piladoras 12-25"


async def test_an_unknown_sheet_lists_the_sheets(httpx_mock):
    _serve(httpx_mock, _make_zip({"libro.xlsx": _workbook(_SIPA_LIKE)}))

    with pytest.raises(ValueError, match="2. Histórico Piladoras 12-25"):
        await read_zip_member(URL, "libro.xlsx", sheet="Mayoristas")


async def test_sheet_is_rejected_for_a_text_member(httpx_mock):
    _serve(httpx_mock, _make_zip({"a.csv": b"x\n1\n"}))

    with pytest.raises(ValueError, match="hojas de cálculo"):
        await read_zip_member(URL, "a.csv", sheet="1")


_INNER_ZIP = _make_zip(
    {
        "DECON_02/IPC_Nacional.csv": "producto;índice\nArroz;107,42\n".encode(),
        "DECON_02/IPC_Quito.csv": b"producto;indice\nArroz;105\n",
    }
)


async def test_reads_a_file_inside_a_nested_zip(httpx_mock):
    _serve(httpx_mock, _make_zip({"DECON_02_IPC.zip": _INNER_ZIP}, method=zipfile.ZIP_STORED))

    result = await read_zip_member(URL, "DECON_02_IPC.zip", inner_member="IPC_Nacional.csv")

    assert result["member_name"] == "DECON_02_IPC.zip/DECON_02/IPC_Nacional.csv"
    assert result["headers"] == ["producto", "índice"]
    assert result["rows"] == [["Arroz", "107.42"]]


async def test_a_nested_zip_without_inner_member_lists_its_files(httpx_mock):
    _serve(httpx_mock, _make_zip({"DECON_02_IPC.zip": _INNER_ZIP}))

    with pytest.raises(ValueError, match=r"inner_member: DECON_02/IPC_Nacional\.csv"):
        await read_zip_member(URL, "DECON_02_IPC.zip")


async def test_inner_member_is_rejected_for_a_plain_member(httpx_mock):
    _serve(httpx_mock, _make_zip({"a.csv": b"x\n1\n"}))

    with pytest.raises(ValueError, match="no es un .zip"):
        await read_zip_member(URL, "a.csv", inner_member="b.csv")


SHEET_URL = "https://example.com/descargas/precios-agroindustria.xlsx"


async def test_empty_member_reads_a_spreadsheet_at_the_url(httpx_mock):
    httpx_mock.add_response(url=SHEET_URL, content=_workbook(_SIPA_LIKE))

    result = await read_zip_member(SHEET_URL, "", sheet="2")

    assert result["member_name"] == "precios-agroindustria.xlsx"
    assert result["sheet"] == "Histórico Piladoras 12-25"
    assert result["rows"][0][-1] == "44.5"


async def test_empty_member_rejects_an_unreadable_url(httpx_mock):
    with pytest.raises(ValueError, match="formato legible"):
        await read_zip_member("https://example.com/informe.pdf", "")


async def test_tool_passes_sheet_and_lists_sheets(httpx_mock):
    httpx_mock.add_response(url=SHEET_URL, content=_workbook(_SIPA_LIKE))
    mcp = MCPServer("t")
    register_read_zip_member_tool(mcp)

    result = await mcp.call_tool(
        "read_zip_member",
        {"url": SHEET_URL, "member": "", "sheet": "Histórico Piladoras 12-25", "format": "json"},
    )

    payload = json.loads(result.content[0].text)
    assert payload["sheets"] == ["ÍNDICE", "Histórico Piladoras 12-25"]
    assert payload["sheet"] == "Histórico Piladoras 12-25"

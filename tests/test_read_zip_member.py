import io
import json
import re
import socket
import struct
import zipfile
import zlib
from pathlib import Path

import httpx
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import csv_reader
from helpers.csv_reader import list_zip_contents, read_zip_member
from tests.xlsb_fixture import make_xlsb
from tools.read_zip_member import register_read_zip_member_tool

URL = "https://example.com/tabulados.zip"
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


@pytest.fixture(autouse=True)
def fresh_zip_blob_cache():
    # Every test uses the same URL; a .zip kept from a Range-less host must not leak.
    csv_reader._blob_cache.clear()
    yield
    csv_reader._blob_cache.clear()


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


def _serve(
    httpx_mock,
    blob: bytes,
    *,
    full_body: bool = False,
    shift: int = 0,
    url: str = URL,
) -> None:
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

    httpx_mock.add_callback(callback, url=url, is_reusable=True)


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


async def test_rejects_a_spreadsheet_too_big_to_open_whole(httpx_mock, monkeypatch):
    monkeypatch.setattr(csv_reader, "_MAX_DECOMPRESSED_BYTES", 100)
    _serve(
        httpx_mock,
        _make_zip({"libro.xlsx": _workbook(_SIPA_LIKE)}, method=zipfile.ZIP_STORED),
    )

    with pytest.raises(ValueError, match="límite"):
        await read_zip_member(URL, "libro.xlsx")


# -- hosts that ignore Range ---------------------------------------------------
#
# The SRI's file host answers 200 with the whole file to a Range request. Up to
# _MAX_NO_RANGE_ZIP_BYTES the .zip is then downloaded whole and read from memory
# through the same parsing as the Range path.


async def test_lists_a_zip_on_a_host_that_ignores_range(httpx_mock):
    blob = _make_zip({"a.csv": b"a\n1\n", "d/": b""})
    _serve(httpx_mock, blob, full_body=True)

    result = await list_zip_contents(URL)

    assert result["total_size_bytes"] == len(blob)
    assert result["total_entries"] == 2
    assert {m["name"]: m["is_dir"] for m in result["members"]} == {
        "a.csv": False,
        "d/": True,
    }


async def test_a_range_less_host_lists_the_same_members_as_a_range_host(httpx_mock):
    blob = _make_zip({"T/INDICE.csv": b"x\n1\n", "T/T1_i1.csv": b"a,b\n1,2\n"})
    other = "https://example.com/otro.zip"
    _serve(httpx_mock, blob)
    _serve(httpx_mock, blob, full_body=True, url=other)

    from_range = await list_zip_contents(URL)
    from_memory = await list_zip_contents(other)

    assert from_memory == {**from_range, "url": other}


@pytest.mark.parametrize("method", [zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED])
async def test_reads_a_member_on_a_host_that_ignores_range(httpx_mock, method):
    blob = _make_zip({"x.csv": b"n\n0\n", "a.csv": b"col,v\nA,1\nB,2\n"}, method=method)
    _serve(httpx_mock, blob, full_body=True)

    result = await read_zip_member(URL, "a.csv")

    assert result["headers"] == ["col", "v"]
    assert result["rows"] == [["A", "1"], ["B", "2"]]
    assert result["uncompressed_size"] == len(b"col,v\nA,1\nB,2\n")


async def test_a_range_less_host_still_checks_the_crc(httpx_mock):
    _serve(httpx_mock, _raw_zip("a.csv", b"a\n1\n", crc=0xDEADBEEF), full_body=True)

    with pytest.raises(ValueError, match="CRC32"):
        await read_zip_member(URL, "a.csv")


async def test_a_range_less_host_still_rejects_an_encrypted_member(httpx_mock):
    _serve(httpx_mock, _raw_zip("a.csv", b"a\n1\n", flags=0x1), full_body=True)

    with pytest.raises(ValueError, match="cifrado"):
        await read_zip_member(URL, "a.csv")


async def test_a_range_less_host_reads_a_text_member_from_its_head(
    httpx_mock, monkeypatch
):
    monkeypatch.setattr(csv_reader, "MAX_DOWNLOAD_BYTES", 2048)
    body = _noise_csv(2000)
    _serve(httpx_mock, _make_zip({"big.csv": body}), full_body=True)

    result = await read_zip_member(URL, "big.csv", max_rows=3)

    assert [row[0] for row in result["rows"]] == ["0", "1", "2"]
    assert result["truncated"] is True
    assert result["uncompressed_size"] == len(body)


async def test_a_range_less_host_reads_zip64_extra_fields(httpx_mock, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(zipfile, "ZIP64_LIMIT", 8)
        blob = _make_zip({"a.csv": b"x,y\n1,2\n", "b.csv": b"n\n" + b"7\n" * 20})
    _serve(httpx_mock, blob, full_body=True)

    listing = await list_zip_contents(URL)
    result = await read_zip_member(URL, "b.csv")

    assert {m["name"]: m["uncompressed_size"] for m in listing["members"]} == {
        "a.csv": 8,
        "b.csv": 42,
    }
    assert result["rows"][0] == ["7"]


async def test_a_range_less_host_reads_the_zip64_end_of_central_directory(
    httpx_mock, monkeypatch
):
    # The 56-byte ZIP64 record sits outside the tail, so it is a range of its own.
    monkeypatch.setattr(csv_reader, "_EOCD_TAIL_BYTES", 42)
    _serve(httpx_mock, _zip64_eocd_zip("datos.csv", b"a,b\n1,2\n"), full_body=True)

    result = await read_zip_member(URL, "datos.csv")

    assert result["rows"] == [["1", "2"]]


async def test_a_range_less_host_with_a_zip_over_the_cap_says_so(
    httpx_mock, monkeypatch
):
    monkeypatch.setattr(csv_reader, "_MAX_NO_RANGE_ZIP_BYTES", 1024 * 1024)
    blob = _make_zip({"a.csv": b"x" * (1024 * 1024 + 10)}, method=zipfile.ZIP_STORED)
    _serve(httpx_mock, blob, full_body=True)

    with pytest.raises(ValueError, match="no soporta HTTP Range") as raised:
        await read_zip_member(URL, "a.csv")

    assert "más de 1 MB" in str(raised.value)
    assert "enlace directo" in str(raised.value)


async def test_listing_then_reading_downloads_a_range_less_zip_once(httpx_mock):
    _serve(httpx_mock, _make_zip({"a.csv": b"a\n1\n"}), full_body=True)

    await list_zip_contents(URL)
    result = await read_zip_member(URL, "a.csv")

    assert result["rows"] == [["1"]]
    # The Range probe, then the one whole download both calls share.
    assert len(httpx_mock.get_requests()) == 2


async def test_a_range_failure_that_is_not_about_range_does_not_fall_back(httpx_mock):
    httpx_mock.add_response(url=URL, status_code=404, is_reusable=True)

    with pytest.raises(httpx.HTTPStatusError):
        await list_zip_contents(URL)

    assert len(httpx_mock.get_requests()) == 1


async def test_a_corrupt_zip_on_a_range_less_host_is_reported_as_not_a_zip(httpx_mock):
    httpx_mock.add_response(url=URL, content=b"whatever bytes", is_reusable=True)

    with pytest.raises(ValueError, match="End Of Central Directory"):
        await list_zip_contents(URL)

    # Nothing was cached for it: the next call downloads again.
    with pytest.raises(ValueError, match="End Of Central Directory"):
        await list_zip_contents(URL)
    assert len(httpx_mock.get_requests()) == 4


async def test_the_in_memory_ranges_match_a_range_server():
    blob = bytes(range(100))

    suffix = await csv_reader._ranged(URL, "bytes=-10", 100, None, blob)
    assert suffix[0] == blob[-10:]
    assert suffix[1]["content-range"] == "bytes 90-99/100"
    assert suffix[2] == 206

    # A suffix longer than the file is the whole file; the end is clamped.
    assert (await csv_reader._ranged(URL, "bytes=-500", 500, None, blob))[0] == blob
    assert (await csv_reader._ranged(URL, "bytes=95-200", 500, None, blob))[0] == blob[95:]
    # The cap truncates the body like the network path does.
    assert (await csv_reader._ranged(URL, "bytes=10-50", 5, None, blob))[0] == blob[10:15]

    with pytest.raises(ValueError, match="corrupto"):
        await csv_reader._ranged(URL, "bytes=100-120", 50, None, blob)


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


# -- review fixes: names over numbers, ODS, inner sizes, inner_member ------------

_YEAR_SHEETS = {
    "2023": [["a"], ["x23"]],
    "2024": [["a"], ["x24"]],
    "Notas": [["n"], ["nota"]],
}


async def test_a_sheet_called_like_a_number_is_read_by_that_name(httpx_mock):
    # "2024" names the second sheet: it must not be read as "the 2024th sheet".
    _serve(httpx_mock, _make_zip({"libro.xlsx": _workbook(_YEAR_SHEETS)}))

    result = await read_zip_member(URL, "libro.xlsx", sheet="2024")

    assert result["sheet"] == "2024"
    assert result["rows"] == [["x24"]]


async def test_a_number_that_names_no_sheet_still_picks_by_position(httpx_mock):
    _serve(httpx_mock, _make_zip({"libro.xlsx": _workbook(_YEAR_SHEETS)}))

    result = await read_zip_member(URL, "libro.xlsx", sheet="3")

    assert result["sheet"] == "Notas"


def test_when_a_name_and_a_position_collide_the_name_wins():
    # Sheets called "2" and "1": "2" is the first sheet by name, not the second by position.
    assert csv_reader._select_sheet(["2", "1"], "2") == 0
    assert csv_reader._select_sheet(["2", "1"], "1") == 1
    assert csv_reader._select_sheet(["A", "B"], "2") == 1
    assert csv_reader._select_sheet(["A", "B"], " b ") == 1


@pytest.mark.parametrize("wanted", ["0", "3", "Mayoristas"])
def test_a_sheet_that_matches_nothing_lists_the_sheets(wanted):
    with pytest.raises(ValueError, match="1. A; 2. B"):
        csv_reader._select_sheet(["A", "B"], wanted)


def _ods(sheets: dict[str, list[str]]) -> bytes:
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableCell, TableRow
    from odf.text import P

    doc = OpenDocumentSpreadsheet()
    for name, values in sheets.items():
        table = Table(name=name)
        for value in values:
            row = TableRow()
            cell = TableCell(valuetype="string")
            cell.addElement(P(text=value))
            row.addElement(cell)
            table.addElement(row)
        doc.spreadsheet.addElement(table)
    buf = io.BytesIO()
    doc.write(buf)
    return buf.getvalue()


async def test_an_ods_sheet_is_selected_by_name_and_by_number(httpx_mock):
    blob = _make_zip({"libro.ods": _ods({"Uno": ["col", "a1"], "Dos": ["col", "b1"]})})
    _serve(httpx_mock, blob)
    _serve(httpx_mock, blob)

    by_name = await read_zip_member(URL, "libro.ods", sheet="Dos")
    by_number = await read_zip_member(URL, "libro.ods", sheet="1")

    assert (by_name["sheet"], by_name["sheets"], by_name["rows"]) == ("Dos", ["Uno", "Dos"], [["b1"]])
    assert (by_number["sheet"], by_number["rows"]) == ("Uno", [["a1"]])


async def test_a_nested_member_reports_the_inner_files_name_and_sizes(httpx_mock):
    body = b"x;y\n" + b"1;2\n" * 1000
    inner = _make_zip({"a.csv": body})
    _serve(httpx_mock, _make_zip({"outer.zip": inner}, method=zipfile.ZIP_STORED))

    result = await read_zip_member(URL, "outer.zip", inner_member="a.csv")

    assert result["member_name"] == "outer.zip/a.csv"
    assert result["outer_member"] == "outer.zip"
    assert result["uncompressed_size"] == len(body)
    assert 0 < result["compressed_size"] < len(body)


async def test_a_plain_member_has_no_outer_member(httpx_mock):
    _serve(httpx_mock, _make_zip({"a.csv": b"x\n1\n"}))

    assert "outer_member" not in await read_zip_member(URL, "a.csv")


async def test_inner_member_with_an_empty_member_is_an_error_not_ignored():
    with pytest.raises(ValueError, match="inner_member solo aplica"):
        await read_zip_member("https://example.com/a.xlsx", "", inner_member="b.csv")


async def test_the_tool_returns_outer_member_for_a_nested_zip(httpx_mock):
    inner = _make_zip({"a.csv": b"x;y\n1;2\n"})
    _serve(httpx_mock, _make_zip({"outer.zip": inner}, method=zipfile.ZIP_STORED))
    mcp = MCPServer("t")
    register_read_zip_member_tool(mcp)

    result = await mcp.call_tool(
        "read_zip_member",
        {"url": URL, "member": "outer.zip", "inner_member": "a.csv", "format": "json"},
    )

    payload = json.loads(result.content[0].text)
    assert payload["outer_member"] == "outer.zip"
    assert payload["member_name"] == "outer.zip/a.csv"


def _noise_csv(rows: int) -> bytes:
    """A CSV whose rows barely compress, so its zipped size tracks its text size."""
    import random

    rng = random.Random(7)
    lines = [f"{i},{rng.getrandbits(64):016x}" for i in range(rows)]
    return ("id,codigo\n" + "\n".join(lines) + "\n").encode()


def _range_lengths(httpx_mock) -> list[int]:
    """Bytes asked for by each Range request that was not the archive's tail."""
    lengths = []
    for request in httpx_mock.get_requests():
        first, last = _RANGE_RE.fullmatch(request.headers["Range"]).groups()
        if first:
            lengths.append(int(last) - int(first) + 1)
    return lengths


@pytest.mark.parametrize("method", [zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED])
async def test_a_text_member_over_the_cap_is_read_from_its_head(
    httpx_mock, monkeypatch, method
):
    monkeypatch.setattr(csv_reader, "MAX_DOWNLOAD_BYTES", 2048)
    body = _noise_csv(2000)
    blob = _make_zip({"big.csv": body}, method=method)
    _serve(httpx_mock, blob)

    result = await read_zip_member(URL, "big.csv", max_rows=3)

    assert result["headers"] == ["id", "codigo"]
    assert [row[0] for row in result["rows"]] == ["0", "1", "2"]
    assert result["truncated"] is True
    assert result["uncompressed_size"] == len(body)
    assert result["compressed_size"] > 2048
    # Only the head crossed the wire, not the whole member.
    assert max(_range_lengths(httpx_mock)) < 2048 + 1024 + 100


async def test_a_member_just_under_the_cap_is_still_read_whole_and_checked(
    httpx_mock, monkeypatch
):
    body = _noise_csv(300)
    blob = _make_zip({"a.csv": body}, method=zipfile.ZIP_STORED)
    monkeypatch.setattr(csv_reader, "MAX_DOWNLOAD_BYTES", len(body) + 10)
    _serve(httpx_mock, blob)

    result = await read_zip_member(URL, "a.csv", max_rows=500)

    assert result["truncated"] is False
    assert len(result["rows"]) == 300


async def test_a_spreadsheet_over_the_old_5mb_cap_is_read_whole(httpx_mock, monkeypatch):
    # A workbook is already compressed, so its member is about as big zipped as
    # not: the 12 MB REESS tabulados failed on the 5 MB wire cap alone.
    monkeypatch.setattr(csv_reader, "MAX_DOWNLOAD_BYTES", 100)
    blob = _make_zip({"libro.xlsx": _workbook(_SIPA_LIKE)}, method=zipfile.ZIP_STORED)
    assert len(blob) > 100
    _serve(httpx_mock, blob)

    result = await read_zip_member(URL, "libro.xlsx", sheet="2")

    assert result["sheet"] == "Histórico Piladoras 12-25"
    assert result["truncated"] is False


async def test_a_nested_zip_over_the_old_5mb_cap_is_read_whole(httpx_mock, monkeypatch):
    monkeypatch.setattr(csv_reader, "MAX_DOWNLOAD_BYTES", 100)
    inner = _make_zip({"a.xlsx": _workbook(_SIPA_LIKE)})
    assert len(inner) > 100
    _serve(httpx_mock, _make_zip({"outer.zip": inner}, method=zipfile.ZIP_STORED))

    result = await read_zip_member(URL, "outer.zip", inner_member="a.xlsx")

    assert result["member_name"] == "outer.zip/a.xlsx"
    assert result["sheets"] == ["ÍNDICE", "Histórico Piladoras 12-25"]


async def test_a_nested_text_file_over_the_cap_is_cut_not_refused(httpx_mock, monkeypatch):
    monkeypatch.setattr(csv_reader, "MAX_DOWNLOAD_BYTES", 2048)
    inner = _make_zip({"big.csv": _noise_csv(2000)})
    _serve(httpx_mock, _make_zip({"outer.zip": inner}, method=zipfile.ZIP_STORED))
    monkeypatch.setattr(csv_reader, "_MAX_DECOMPRESSED_BYTES", 10 * 1024 * 1024)

    result = await read_zip_member(URL, "outer.zip", inner_member="big.csv", max_rows=2)

    assert [row[0] for row in result["rows"]] == ["0", "1"]
    assert result["truncated"] is True


def _oem_named(blob: bytes, placeholder: bytes, name: str) -> bytes:
    """Swap an ASCII placeholder name for the cp850 bytes Windows archivers write."""
    swapped = name.encode("cp850")
    assert len(swapped) == len(placeholder) and blob.count(placeholder) == 2
    return blob.replace(placeholder, swapped)


async def test_member_names_written_in_cp850_keep_their_accented_capitals(httpx_mock):
    # "RÍOS" is bytes 52 D6 4F 53: cp850 reads it as Í, cp437 as "╓".
    blob = _oem_named(_make_zip({"R_OS/lista.csv": b"a\n1\n"}), b"R_OS", "RÍOS")
    _serve(httpx_mock, blob)

    listing = await list_zip_contents(URL)
    result = await read_zip_member(URL, "RÍOS/lista.csv")

    assert [m["name"] for m in listing["members"]] == ["RÍOS/lista.csv"]
    assert result["member_name"] == "RÍOS/lista.csv"


async def test_nested_member_names_written_in_cp850_keep_their_accented_capitals(httpx_mock):
    inner = _oem_named(_make_zip({"1._ndice.csv": b"a;b\n1;2\n"}), b"_ndice", "Índice")
    _serve(httpx_mock, _make_zip({"outer.zip": inner}, method=zipfile.ZIP_STORED))

    with pytest.raises(ValueError, match=r"inner_member: 1\.Índice\.csv"):
        await read_zip_member(URL, "outer.zip")
    result = await read_zip_member(URL, "outer.zip", inner_member="1.Índice.csv")

    assert result["member_name"] == "outer.zip/1.Índice.csv"
    assert result["rows"] == [["1", "2"]]


_LEGACY_BOOK = {
    "ÍNDICE": [["Contenido"], ["Precios"]],
    "Precios 2024": [["Año", "Mes", "Producto", "Precio"], [2024, "Octubre", "Arroz", 44.5]],
}
_XLS_TWO_SHEETS = (Path(__file__).parent / "fixtures" / "dos_hojas.xls").read_bytes()


@pytest.mark.parametrize(
    ("member", "blob"),
    [
        ("libro.xls", _XLS_TWO_SHEETS),
        ("libro.xlsb", make_xlsb(_LEGACY_BOOK)),
    ],
)
async def test_legacy_spreadsheets_list_their_sheets_and_pick_one(httpx_mock, member, blob):
    _serve(httpx_mock, _make_zip({member: blob}))

    first = await read_zip_member(URL, member)
    by_name = await read_zip_member(URL, member, sheet="precios 2024")
    by_number = await read_zip_member(URL, member, sheet="2")

    assert first["sheet"] == "ÍNDICE"
    assert first["sheets"] == ["ÍNDICE", "Precios 2024"]
    assert first["headers"] == ["Contenido"]
    for picked in (by_name, by_number):
        assert picked["sheet"] == "Precios 2024"
        assert picked["headers"] == ["Año", "Mes", "Producto", "Precio"]
        assert picked["rows"] == [["2024", "Octubre", "Arroz", "44.5"]]


@pytest.mark.parametrize(
    ("member", "blob"),
    [
        ("libro.xls", _XLS_TWO_SHEETS),
        ("libro.xlsb", make_xlsb(_LEGACY_BOOK)),
    ],
)
async def test_an_unknown_sheet_in_a_legacy_spreadsheet_lists_the_sheets(
    httpx_mock, member, blob
):
    _serve(httpx_mock, _make_zip({member: blob}))

    with pytest.raises(ValueError, match="2. Precios 2024"):
        await read_zip_member(URL, member, sheet="Mayoristas")


async def test_a_legacy_spreadsheet_published_at_a_url_reads_by_sheet(httpx_mock):
    # SIPA publishes .xls files directly: the 74-sheet agricultural census is one.
    url = "https://example.com/descargas/censo.xls"
    httpx_mock.add_response(url=url, content=_XLS_TWO_SHEETS)

    result = await read_zip_member(url, "", sheet="Precios 2024")

    assert result["member_name"] == "censo.xls"
    assert result["rows"] == [["2024", "Octubre", "Arroz", "44.5"]]


async def test_a_legacy_spreadsheet_inside_a_nested_zip_reads_by_sheet(httpx_mock):
    inner = _make_zip({"libro.xlsb": make_xlsb(_LEGACY_BOOK)})
    _serve(httpx_mock, _make_zip({"outer.zip": inner}, method=zipfile.ZIP_STORED))

    result = await read_zip_member(URL, "outer.zip", inner_member="libro.xlsb", sheet="2")

    assert result["member_name"] == "outer.zip/libro.xlsb"
    assert result["sheet"] == "Precios 2024"


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (2024.0, "2024"),
        (44.5, "44.5"),
        (-3.0, "-3"),
        (1e20, "1e+20"),
        (float("inf"), "inf"),
        (True, "True"),
        ("texto", "texto"),
        (None, ""),
    ],
)
def test_cell_text_drops_the_point_zero_of_whole_numbers_only(value, text):
    assert csv_reader._cell_text(value) == text


@pytest.mark.parametrize(
    ("value", "expected_mb"),
    [("", 400), ("  ", 400), ("abc", 400), ("0", 400), ("-5", 400), ("64", 64), ("9999", 1024)],
)
def test_the_no_range_cap_reads_its_environment_variable(monkeypatch, value, expected_mb):
    monkeypatch.setenv("ECUADOR_MCP_NO_RANGE_ZIP_MB", value)

    assert csv_reader._no_range_zip_limit() == expected_mb * 1024 * 1024

"""aggregate_csv reads a CSV inside a .zip as a stream, and a host without Range
can hand over a .zip far past memory.

The SRI's RUC file for Pichincha is 156 MB zipped and 740 MB of text: it could
only be read from its head (5 MB), and a host without Range had to download the
whole .zip into memory, so anything over 20 MB was refused unless the operator
raised ECUADOR_MCP_NO_RANGE_ZIP_MB.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import socket
import zipfile
import zlib
from decimal import Decimal

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from helpers import csv_aggregate, csv_reader
from helpers.csv_reader import (
    ZipMemberSpan,
    iter_zip_member,
    list_zip_contents,
    read_zip_member,
)
from helpers.zip_blob import SpooledBlob
from tools.aggregate_csv import register_aggregate_csv_tool

URL = "https://example.com/ruc/guayas.zip"
MEMBER = "guayas/ruc.csv"
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    csv_reader._blob_cache.clear()
    csv_aggregate._cache.clear()
    yield
    csv_reader._blob_cache.clear()
    csv_aggregate._cache.clear()


def _rows(count: int = 50) -> bytes:
    lines = ["PROVINCIA|ESTADO|MONTO"]
    for number in range(count):
        province = ("GUAYAS", "SANTA ELENA", "EL ORO")[number % 3]
        state = "ACTIVO" if number % 4 else "SUSPENDIDO"
        lines.append(f"{province}|{state}|{number},50")
    return ("\r\n".join(lines) + "\r\n").encode()


def _make_zip(members: dict[str, bytes], method: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=method) as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _serve(
    httpx_mock, blob: bytes, *, ranges: bool = True, identity_only: bool = False
) -> None:
    """Answer Range requests from `blob`, or 200 with the whole file every time.

    `identity_only` mimics descargas.sri.gob.ec, which ignores Range unless the
    request says Accept-Encoding: identity.
    """
    total = len(blob)

    def callback(request: httpx.Request) -> httpx.Response:
        if not ranges or "Range" not in request.headers:
            return httpx.Response(200, content=blob)
        if identity_only and request.headers.get("Accept-Encoding") != "identity":
            return httpx.Response(200, content=blob)
        first, last = _RANGE_RE.fullmatch(request.headers["Range"]).groups()
        if first == "":
            start, end = max(total - int(last), 0), total - 1
        else:
            start, end = int(first), min(int(last), total - 1)
        return httpx.Response(
            206,
            content=blob[start : end + 1],
            headers={"Content-Range": f"bytes {start}-{end}/{total}"},
        )

    httpx_mock.add_callback(callback, url=URL, is_reusable=True)


async def _aggregate(**kwargs):
    kwargs.setdefault("group_by", ["PROVINCIA"])
    kwargs.setdefault("sum_columns", ["MONTO"])
    kwargs.setdefault("filters", {})
    kwargs.setdefault("member", MEMBER)
    return await csv_aggregate.aggregate_url(URL, **kwargs)


def _expected_by_province(raw: bytes) -> dict[str, tuple[int, Decimal]]:
    out: dict[str, list] = {}
    for line in raw.decode().splitlines()[1:]:
        province, _state, amount = line.split("|")
        entry = out.setdefault(province, [0, Decimal(0)])
        entry[0] += 1
        entry[1] += Decimal(amount.replace(",", "."))
    return {k: (v[0], v[1]) for k, v in out.items()}


# -- aggregate_csv over a member ----------------------------------------------


@pytest.mark.parametrize("method", [zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED])
async def test_groups_a_member_through_range_requests(httpx_mock, method):
    raw = _rows()
    _serve(httpx_mock, _make_zip({MEMBER: raw, "guayas/LEEME.txt": b"hola"}, method))

    result = await _aggregate()

    expected = _expected_by_province(raw)
    got = {row[0]: (row[1], Decimal(str(row[2]))) for row in result["rows"]}
    assert got == expected
    assert result["filas_leidas"] == 50
    assert result["miembro"] == MEMBER
    assert result["bytes_leidos"] == len(raw)
    assert csv_reader._blob_cache.get(URL) is None  # Range host: no whole download


async def test_a_member_split_over_many_requests_and_chunks_adds_up(httpx_mock, monkeypatch):
    raw = _rows(5000)
    monkeypatch.setattr(csv_reader, "_SPAN_REQUEST_BYTES", 1000)
    monkeypatch.setattr(csv_reader, "_STREAM_READ_BYTES", 700)
    monkeypatch.setattr(csv_reader, "_STREAM_OUT_BYTES", 900)
    monkeypatch.setattr(csv_aggregate, "_STREAM_BUFFER_BYTES", 512)
    _serve(httpx_mock, _make_zip({MEMBER: raw}))

    result = await _aggregate(filters={"ESTADO": ["ACTIVO"]})

    kept = b"PROVINCIA|ESTADO|MONTO\r\n" + b"".join(
        line + b"\r\n" for line in raw.splitlines()[1:] if b"|ACTIVO|" in line
    )
    expected = _expected_by_province(kept)
    assert {row[0]: (row[1], Decimal(str(row[2]))) for row in result["rows"]} == expected
    assert result["filas_leidas"] == 5000
    assert result["filas_coinciden"] == sum(count for count, _ in expected.values())
    assert len(httpx_mock.get_requests()) > 6  # tail, directory, header, several spans


async def test_range_requests_say_identity_so_the_sri_host_honors_them(httpx_mock):
    raw = _rows()
    _serve(httpx_mock, _make_zip({MEMBER: raw}), identity_only=True)

    listing = await list_zip_contents(URL)
    result = await _aggregate()

    assert [m["name"] for m in listing["members"]] == [MEMBER]
    assert result["filas_leidas"] == 50
    assert csv_reader._blob_cache.get(URL) is None  # read by ranges, never downloaded whole
    assert all(r.headers["Accept-Encoding"] == "identity" for r in httpx_mock.get_requests())


async def test_a_host_without_range_hands_over_the_whole_zip(httpx_mock):
    raw = _rows()
    _serve(httpx_mock, _make_zip({MEMBER: raw}), ranges=False)

    result = await _aggregate()

    assert result["filas_leidas"] == 50
    assert csv_reader._blob_cache.get(URL) is not None


async def test_a_zip_past_memory_goes_to_a_temporary_file_and_is_reused(httpx_mock, monkeypatch):
    raw = _rows(2000)
    monkeypatch.setattr(csv_reader, "_NO_RANGE_ZIP_RAM_BYTES", 64)
    blob = _make_zip({MEMBER: raw, "guayas/LEEME.txt": b"hola"})
    _serve(httpx_mock, blob, ranges=False)

    listing = await list_zip_contents(URL)
    cached = csv_reader._blob_cache.get(URL)
    read = await read_zip_member(URL, MEMBER, max_rows=3)
    result = await _aggregate()

    assert isinstance(cached, SpooledBlob) and cached.on_disk
    assert len(cached) == len(blob) == listing["total_size_bytes"]
    # The preview turns a decimal comma into a point; the totals read the original.
    assert read["rows"][0] == ["GUAYAS", "SUSPENDIDO", "0.50"]
    assert len(read["rows"]) == 3
    assert result["filas_leidas"] == 2000
    whole = [r for r in httpx_mock.get_requests() if "Range" not in r.headers]
    assert len(whole) == 1  # downloaded once, then read from the temporary file


async def test_two_calls_for_the_same_big_zip_share_one_download(httpx_mock, monkeypatch):
    monkeypatch.setattr(csv_reader, "_NO_RANGE_ZIP_RAM_BYTES", 64)
    _serve(httpx_mock, _make_zip({MEMBER: _rows(500)}), ranges=False)

    await asyncio.gather(list_zip_contents(URL), list_zip_contents(URL), _aggregate())

    whole = [r for r in httpx_mock.get_requests() if "Range" not in r.headers]
    assert len(whole) == 1


async def test_a_zip_over_the_download_cap_is_refused_and_leaves_no_file(httpx_mock, monkeypatch):
    monkeypatch.setattr(csv_reader, "_MAX_NO_RANGE_ZIP_BYTES", 1024)
    monkeypatch.setattr(csv_reader, "_NO_RANGE_ZIP_RAM_BYTES", 64)
    _serve(httpx_mock, _make_zip({MEMBER: _rows(2000)}, zipfile.ZIP_STORED), ranges=False)

    with pytest.raises(ValueError, match="pesa más de"):
        await _aggregate()

    assert csv_reader._blob_cache.get(URL) is None


async def test_a_member_over_the_size_limits_is_refused_not_summed_in_part(httpx_mock, monkeypatch):
    _serve(httpx_mock, _make_zip({MEMBER: _rows(2000)}, zipfile.ZIP_STORED))
    monkeypatch.setattr(csv_aggregate, "ZIP_MAX_UNCOMPRESSED_BYTES", 1024 * 1024)
    monkeypatch.setattr(csv_aggregate, "ZIP_MAX_COMPRESSED_BYTES", 10)

    with pytest.raises(ValueError, match="comprimido, por encima del límite"):
        await _aggregate()


async def test_a_member_that_is_not_text_a_folder_or_missing_is_refused(httpx_mock):
    _serve(httpx_mock, _make_zip({"datos.xlsx": b"x", "carpeta/": b"", MEMBER: _rows()}))

    with pytest.raises(ValueError, match="no es texto delimitado"):
        await _aggregate(member="datos.xlsx")
    with pytest.raises(ValueError, match="carpeta"):
        await _aggregate(member="carpeta/")
    with pytest.raises(ValueError, match="No hay ningún archivo"):
        await _aggregate(member="otro.csv")


async def test_a_zip_without_member_points_to_member(httpx_mock):
    with pytest.raises(ValueError, match="pasa en member"):
        await csv_aggregate.aggregate_url(URL, group_by=[], sum_columns=[], filters={})

    assert httpx_mock.get_requests() == []


async def test_a_repeat_question_is_answered_from_memory(httpx_mock):
    _serve(httpx_mock, _make_zip({MEMBER: _rows()}))

    first = await _aggregate()
    requests_after_first = len(httpx_mock.get_requests())
    second = await _aggregate()

    assert second == first
    assert len(httpx_mock.get_requests()) == requests_after_first


def test_a_deadline_stops_a_read_that_runs_too_long():
    with pytest.raises(ValueError, match="tardó más de"):
        csv_aggregate.aggregate_stream(
            io.BytesIO(_rows()),
            encoding="utf-8",
            group_by=[],
            sum_columns=[],
            filters={},
            deadline_seconds=-1,
        )


# -- iter_zip_member: a damaged .zip must not give a total ---------------------


def _span(raw: bytes, *, method: int = 8, **overrides) -> ZipMemberSpan:
    data = zlib.compress(raw, 9)[2:-4] if method == 8 else raw
    fields = {
        "name": "ruc.csv",
        "method": method,
        "compressed_size": len(data),
        "uncompressed_size": len(raw),
        "crc32": zlib.crc32(raw),
        "source": b"PADDING" + data,
        "offset": 7,
    }
    fields.update(overrides)
    return ZipMemberSpan(**fields)


@pytest.mark.parametrize("method", [8, 0])
def test_a_sound_member_comes_back_whole(method):
    raw = _rows(300)

    assert b"".join(iter_zip_member(_span(raw, method=method))) == raw


def test_a_member_that_expands_past_its_declared_size_fails():
    raw = _rows(300)

    with pytest.raises(ValueError, match="más datos que el tamaño declarado"):
        b"".join(iter_zip_member(_span(raw, uncompressed_size=100)))


def test_a_member_that_ends_short_of_its_declared_size_fails():
    raw = _rows(300)

    with pytest.raises(ValueError, match="tamaño descomprimido inesperado"):
        b"".join(iter_zip_member(_span(raw, uncompressed_size=len(raw) + 5)))


def test_a_wrong_crc_fails():
    with pytest.raises(ValueError, match="CRC32 no coincide"):
        b"".join(iter_zip_member(_span(_rows(300), crc32=123)))


def test_cut_off_compressed_data_fails():
    raw = _rows(2000)
    span = _span(raw)
    cut = ZipMemberSpan(**{**span.__dict__, "compressed_size": span.compressed_size // 2})

    with pytest.raises(ValueError, match="corrupto"):
        b"".join(iter_zip_member(cut))


def test_garbage_in_place_of_a_deflate_stream_fails():
    span = _span(_rows(300), source=b"\xff" * 400, compressed_size=300, offset=0)

    with pytest.raises(ValueError, match="corrupto"):
        b"".join(iter_zip_member(span))


def test_a_source_shorter_than_the_member_fails():
    span = _span(_rows(300), source=b"short", offset=0)

    with pytest.raises(ValueError, match="datos incompletos"):
        b"".join(iter_zip_member(span))


# -- SpooledBlob ---------------------------------------------------------------


def test_a_spooled_blob_slices_like_bytes_in_memory_and_on_disk():
    data = bytes(range(256)) * 40
    small = SpooledBlob(ram_bytes=len(data) + 1)
    big = SpooledBlob(ram_bytes=100)
    for blob in (small, big):
        for start in range(0, len(data), 1000):
            blob.write(data[start : start + 1000])

    assert not small.on_disk and big.on_disk
    for blob in (small, big):
        assert len(blob) == len(data)
        assert blob[0:10] == data[0:10]
        assert blob[len(data) - 5 : len(data) + 50] == data[-5:]
        assert blob[500:2500][:300] == data[500:800]
        assert blob[len(data) + 10 : len(data) + 20] == b""
    small.close()
    big.close()


def test_a_spooled_blob_refuses_a_stepped_slice():
    blob = SpooledBlob(ram_bytes=10)
    blob.write(b"abcdef")

    with pytest.raises(TypeError):
        blob[::2]


# -- the tool ------------------------------------------------------------------


async def test_the_tool_reads_a_member_and_names_it(httpx_mock):
    raw = _rows()
    _serve(httpx_mock, _make_zip({MEMBER: raw}))
    server = MCPServer("test")
    register_aggregate_csv_tool(server)

    args = {
        "url": URL,
        "member": MEMBER,
        "group_by": "PROVINCIA",
        "sum_columns": "MONTO",
    }
    text = (await server.call_tool("aggregate_csv", args)).content[0].text
    payload = json.loads(
        (await server.call_tool("aggregate_csv", {**args, "format": "json"})).content[0].text
    )

    assert f"Miembro del .zip: {MEMBER}" in text
    assert payload["miembro"] == MEMBER
    assert payload["filas_leidas"] == 50


async def test_the_tool_without_member_still_refuses_a_zip_url():
    server = MCPServer("test")
    register_aggregate_csv_tool(server)

    with pytest.raises(Exception, match="member"):
        await server.call_tool("aggregate_csv", {"url": URL})

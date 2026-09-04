import gzip
import io
import socket
import ssl
import struct
import tarfile
import zipfile
import zlib

import httpx
import pytest

import helpers.csv_reader as csv_reader_module
from helpers.csv_reader import (
    MAX_DOWNLOAD_BYTES,
    _gunzip_capped,
    _parse_csv_bytes,
    _parse_eocd,
    download_bytes,
    list_zip_contents,
    normalize_eu_decimal_columns,
    preview_ods,
    preview_targz,
    preview_xlsb,
    preview_zip,
    sniff_content_type,
    strip_geometry_columns,
)


def test_strip_geometry_columns_by_name():
    headers = ["id", "nombre", "geom"]
    rows = [["1", "Quito", "POLYGON((-78.5 -0.2, -78.4 -0.1, -78.5 -0.2))"]]

    new_headers, new_rows, dropped = strip_geometry_columns(headers, rows)

    assert new_headers == ["id", "nombre"]
    assert new_rows == [["1", "Quito"]]
    assert dropped == ["geom"]


def test_strip_geometry_columns_by_content():
    headers = ["id", "the_shape"]
    rows = [
        ["1", "MULTIPOLYGON(((-78.5 -0.2, -78.4 -0.1, -78.5 -0.2)))"],
        ["2", "MULTIPOLYGON(((-79.5 -1.2, -79.4 -1.1, -79.5 -1.2)))"],
    ]

    new_headers, new_rows, dropped = strip_geometry_columns(headers, rows)

    assert new_headers == ["id"]
    assert new_rows == [["1"], ["2"]]
    assert dropped == ["the_shape"]


def test_strip_geometry_columns_no_geometry():
    headers = ["id", "nombre"]
    rows = [["1", "Quito"]]

    new_headers, new_rows, dropped = strip_geometry_columns(headers, rows)

    assert new_headers == headers
    assert new_rows == rows
    assert dropped == []


def test_normalize_eu_decimal_columns():
    headers = ["provincia", "monto"]
    rows = [["Pichincha", "7.760,2"], ["Guayas", "168,15"]]

    new_rows, converted = normalize_eu_decimal_columns(headers, rows)

    assert converted == ["monto"]
    assert new_rows == [["Pichincha", "7760.2"], ["Guayas", "168.15"]]


def test_normalize_eu_decimal_columns_negative_value():
    headers = ["variacion"]
    rows = [["-1.234,5"]]

    new_rows, converted = normalize_eu_decimal_columns(headers, rows)

    assert converted == ["variacion"]
    assert new_rows == [["-1234.5"]]


def test_normalize_eu_decimal_columns_leaves_ambiguous_columns():
    headers = ["fecha", "id"]
    rows = [["2026-01-01", "100"], ["2026-01-02", "200"]]

    new_rows, converted = normalize_eu_decimal_columns(headers, rows)

    assert converted == []
    assert new_rows == rows


async def test_download_bytes_exactly_at_limit_is_not_truncated(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    body = b"x" * MAX_DOWNLOAD_BYTES
    url = "https://example.com/exact.bin"
    httpx_mock.add_response(url=url, content=body)

    content, truncated = await download_bytes(url)

    assert len(content) == MAX_DOWNLOAD_BYTES
    assert truncated is False


async def test_download_bytes_over_limit_is_truncated(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    body = b"x" * (MAX_DOWNLOAD_BYTES + 1)
    url = "https://example.com/over.bin"
    httpx_mock.add_response(url=url, content=body)

    _content, truncated = await download_bytes(url)

    assert truncated is True


def _make_targz(members: dict[str, bytes]) -> bytes:
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return gzip.compress(tar_buf.getvalue())


def test_gunzip_capped_returns_full_payload_when_under_cap():
    raw = b"hello world" * 100
    payload = gzip.compress(raw)

    decompressed, capped = _gunzip_capped(payload, cap=1024 * 1024)

    assert capped is False
    assert decompressed == raw


def test_gunzip_capped_stops_at_cap():
    payload = gzip.compress(b"x" * (5 * 1024 * 1024))

    decompressed, capped = _gunzip_capped(payload, cap=1024)

    assert capped is True
    assert len(decompressed) == 1024


class _SpyDecompressor:
    """Wraps a real zlib decompressor (a C type -- its methods can't be
    monkeypatched directly) to record the largest single decompress() output.
    """

    def __init__(self, real):
        self._real = real
        self.max_seen = 0

    def decompress(self, data, max_length=0):
        out = self._real.decompress(data, max_length)
        self.max_seen = max(self.max_seen, len(out))
        return out

    def flush(self, length=None):
        return self._real.flush(length) if length is not None else self._real.flush()

    @property
    def unconsumed_tail(self):
        return self._real.unconsumed_tail


def test_gunzip_capped_never_decompresses_past_cap_in_one_call(monkeypatch):
    # A single highly-compressible chunk can expand far past `cap` in one
    # zlib.decompress() call unless max_length is passed -- the bug this
    # regression test targets. 50 MB of zeros compresses to well under one
    # 64 KB chunk, so if the cap isn't enforced *within* that one call, this
    # would fully materialize 50 MB before the length check ever runs.
    payload = gzip.compress(b"\x00" * (50 * 1024 * 1024))
    assert len(payload) < 65536

    real_decompressobj = zlib.decompressobj
    spies: list[_SpyDecompressor] = []

    def spy_decompressobj(*args, **kwargs):
        spy = _SpyDecompressor(real_decompressobj(*args, **kwargs))
        spies.append(spy)
        return spy

    monkeypatch.setattr(csv_reader_module.zlib, "decompressobj", spy_decompressobj)

    decompressed, capped = _gunzip_capped(payload, cap=1024)

    assert capped is True
    assert len(decompressed) == 1024
    assert spies[0].max_seen <= 1024


async def test_preview_targz_reads_embedded_csv(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    csv_bytes = b"provincia,monto\nPichincha,100\nGuayas,200\n"
    gz_bytes = _make_targz({"datos.csv": csv_bytes})
    url = "https://example.com/datos.tar.gz"
    httpx_mock.add_response(url=url, content=gz_bytes)

    result = await preview_targz(url)

    assert result["headers"] == ["provincia", "monto"]
    assert result["rows"] == [["Pichincha", "100"], ["Guayas", "200"]]
    assert result["format"] == "tar_gz"
    assert result["member_name"] == "datos.csv"
    assert result["truncated"] is False


async def test_preview_targz_picks_csv_member_over_other_files(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    gz_bytes = _make_targz(
        {
            "readme.txt": b"metadata not the data",
            "datos.csv": b"a,b\n1,2\n",
        }
    )
    url = "https://example.com/mixto.tar.gz"
    httpx_mock.add_response(url=url, content=gz_bytes)

    result = await preview_targz(url)

    assert result["member_name"] == "datos.csv"
    assert result["headers"] == ["a", "b"]


def _make_zip(members: dict[str, bytes]) -> bytes:
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return zip_buf.getvalue()


async def test_preview_zip_reads_embedded_csv(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    csv_bytes = b"provincia,monto\nPichincha,100\nGuayas,200\n"
    zip_bytes = _make_zip({"datos.csv": csv_bytes})
    url = "https://example.com/datos.zip"
    httpx_mock.add_response(url=url, content=zip_bytes)

    result = await preview_zip(url)

    assert result["headers"] == ["provincia", "monto"]
    assert result["rows"] == [["Pichincha", "100"], ["Guayas", "200"]]
    assert result["format"] == "zip"
    assert result["member_name"] == "datos.csv"
    assert result["truncated"] is False


async def test_preview_zip_picks_csv_member_over_other_files(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    zip_bytes = _make_zip(
        {
            "readme.txt": b"metadata not the data",
            "datos.csv": b"a,b\n1,2\n",
        }
    )
    url = "https://example.com/mixto.zip"
    httpx_mock.add_response(url=url, content=zip_bytes)

    result = await preview_zip(url)

    assert result["member_name"] == "datos.csv"
    assert result["headers"] == ["a", "b"]


async def test_preview_zip_rejects_corrupt_archive(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    url = "https://example.com/corrupto.zip"
    httpx_mock.add_response(url=url, content=b"not a real zip file")

    with pytest.raises(ValueError, match="no se pudo leer"):
        await preview_zip(url)


async def test_sniff_content_type_returns_header(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    url = "https://example.com/download?id=123"
    httpx_mock.add_response(
        url=url, headers={"content-type": "text/csv; charset=utf-8"}, content=b"a,b\n1,2\n"
    )

    content_type = await sniff_content_type(url)

    assert content_type == "text/csv; charset=utf-8"


async def test_download_bytes_retries_with_os_trust_on_cert_error(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    url = "https://www.censoecuador.gob.ec/data-y-resultados/"
    exc = httpx.ConnectError("cert failure", request=httpx.Request("GET", url))
    exc.__context__ = ssl.SSLCertVerificationError(
        "unable to get local issuer certificate"
    )
    httpx_mock.add_exception(exc)
    httpx_mock.add_response(url=url, content=b"real page content")

    content, truncated = await download_bytes(url, raise_for_status=False)

    assert content == b"real page content"
    assert truncated is False


async def test_download_bytes_raise_for_status_false_tolerates_error_status(
    httpx_mock, monkeypatch
):
    # censoecuador.gob.ec's /data-y-resultados/ page returns HTTP 404 (a
    # WordPress/Elementor bug) while still serving its real page content --
    # confirmed live. Every other caller keeps the default (raise on error).
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    url = "https://example.com/broken-status-real-content"
    httpx_mock.add_response(url=url, status_code=404, content=b"real content anyway")

    content, truncated = await download_bytes(url, raise_for_status=False)

    assert content == b"real content anyway"
    assert truncated is False


async def test_download_bytes_default_still_raises_on_error_status(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    url = "https://example.com/genuinely-missing"
    httpx_mock.add_response(url=url, status_code=404, content=b"not found")

    with pytest.raises(httpx.HTTPStatusError):
        await download_bytes(url)


async def test_sniff_content_type_returns_none_on_connection_failure(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    url = "https://example.com/download?id=123"
    httpx_mock.add_exception(httpx.ConnectError("boom", request=httpx.Request("GET", url)))

    assert await sniff_content_type(url) is None


async def test_preview_zip_over_5mb_gives_actionable_truncation_message(httpx_mock, monkeypatch):
    # Confirmed against a real 17MB .zip on the live portal: a download cut
    # off at MAX_DOWNLOAD_BYTES is missing the zip's central directory
    # (always at the end of the file), so zipfile fails outright with "File
    # is not a zip file" -- not a partial/degraded read. This reproduces
    # that with a real (uncompressed, so size is predictable) zip padded
    # past the cap, and checks we say why instead of just "corrupt".
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    padding = b"1,2\n" * (MAX_DOWNLOAD_BYTES // 4 + 10)
    big_zip = _make_zip({"datos.csv": b"a,b\n" + padding})
    assert len(big_zip) > MAX_DOWNLOAD_BYTES

    url = "https://example.com/grande.zip"
    httpx_mock.add_response(url=url, content=big_zip)

    with pytest.raises(ValueError, match="supera el límite de 5 MB"):
        await preview_zip(url)


async def test_preview_xlsb_over_5mb_gives_actionable_truncation_message(
    httpx_mock, monkeypatch
):
    # .xlsb is a ZIP container too (BIFF12 records instead of XLSX's XML),
    # so it fails the exact same way as a truncated .zip: confirmed against
    # a real 9.3MB resource (Registro Civil's "Defunciones Generales") --
    # zipfile can't open it at all once the central directory is cut off.
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    # The truncation check happens before any parsing, so the padding
    # doesn't need to be valid xlsb content -- only its size matters.
    big_body = b"0" * (MAX_DOWNLOAD_BYTES + 10)
    url = "https://example.com/defunciones.xlsb"
    httpx_mock.add_response(url=url, content=big_body)

    with pytest.raises(ValueError, match="supera el límite de 5 MB"):
        await preview_xlsb(url)


async def test_preview_zip_with_no_tabular_member_gives_clear_message(httpx_mock, monkeypatch):
    # Confirmed against a real GIS raster .zip on the live portal
    # (.lyr/.tif/.tif.aux.xml, no CSV at all): silently parsing the first
    # binary file as CSV crashed with a raw csv.Error. Now it should say
    # plainly that there's no tabular content, listing what is actually
    # inside.
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    zip_bytes = _make_zip({"mapa.tif": b"\x00\x01\x02not really a tiff"})
    url = "https://example.com/raster.zip"
    httpx_mock.add_response(url=url, content=zip_bytes)

    with pytest.raises(ValueError, match="no contiene ningún archivo"):
        await preview_zip(url)


async def test_preview_targz_with_no_tabular_member_gives_clear_message(
    httpx_mock, monkeypatch
):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    gz_bytes = _make_targz({"mapa.tif": b"\x00\x01\x02not really a tiff"})
    url = "https://example.com/raster.tar.gz"
    httpx_mock.add_response(url=url, content=gz_bytes)

    with pytest.raises(ValueError, match="no contiene ningún archivo"):
        await preview_targz(url)


def test_parse_csv_bytes_raises_actionable_error_for_malformed_csv():
    # Real repro of a bare, unquoted carriage return inside a field --
    # Python's csv module refuses to parse this at all. Found for real
    # while investigating why a live-portal .zip's picked member crashed
    # with a raw, unhandled csv.Error instead of a message.
    raw = b'a,b\r"x\ry,2\r'

    with pytest.raises(ValueError, match="no se pudo parsear como CSV"):
        _parse_csv_bytes(raw, max_rows=20)


def test_parse_csv_bytes_picks_semicolon_over_comma_heavy_prose_field():
    # Real repro against Contraloría's audit-report CSVs: a naive whole-
    # sample character count picked ',' because free-text description
    # fields (Spanish prose) contained more commas than the file's actual
    # ';' delimiter had occurrences, splitting every row into one giant
    # unparsed field instead of real columns.
    raw = (
        b"id;entidad;diligencia\r\n"
        b"1;MINISTERIO A;Examen sobre procesos, contratos, convenios y anexos\r\n"
        b"2;MINISTERIO B;Auditoria de gastos, ingresos, activos y pasivos\r\n"
    )

    result = _parse_csv_bytes(raw, max_rows=20)

    assert result["headers"] == ["id", "entidad", "diligencia"]
    assert result["rows"][0] == [
        "1",
        "MINISTERIO A",
        "Examen sobre procesos, contratos, convenios y anexos",
    ]


def _make_ods(rows: list[list[str]], pad_columns: int = 0, pad_rows: int = 0) -> bytes:
    """Build a real .ods file with `rows`, optionally followed by a padded
    trailing empty column (on the header row) and/or a padded trailing block
    of empty rows -- both are how real spreadsheet editors encode unused
    grid space, via numbercolumnsrepeated/numberrowsrepeated attributes."""
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableCell, TableRow
    from odf.text import P

    doc = OpenDocumentSpreadsheet()
    table = Table(name="Hoja1")
    for i, row_values in enumerate(rows):
        row = TableRow()
        for value in row_values:
            cell = TableCell(valuetype="string")
            cell.addElement(P(text=value))
            row.addElement(cell)
        if i == 0 and pad_columns:
            row.addElement(TableCell(valuetype="string", numbercolumnsrepeated=pad_columns))
        table.addElement(row)
    if pad_rows:
        blank_row = TableRow(numberrowsrepeated=pad_rows)
        blank_row.addElement(TableCell(valuetype="string", numbercolumnsrepeated=10))
        table.addElement(blank_row)
    doc.spreadsheet.addElement(table)
    buf = io.BytesIO()
    doc.write(buf)
    return buf.getvalue()


def test_parse_eocd_rejects_zip64_sentinels():
    tail = struct.pack(
        "<4sHHHHIIH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0
    )
    with pytest.raises(ValueError, match="ZIP64"):
        _parse_eocd(tail)


async def test_list_zip_contents_lists_members_via_single_range(httpx_mock, monkeypatch):
    # A small archive: the central directory sits well inside the default
    # tail window, so this should resolve with a single Range request.
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    zip_bytes = _make_zip({"data.csv": b"a,b\n1,2\n", "readme.txt": b"hello world"})
    total = len(zip_bytes)
    url = "https://example.com/small.zip"

    httpx_mock.add_response(
        url=url,
        status_code=206,
        content=zip_bytes,
        headers={"Content-Range": f"bytes 0-{total - 1}/{total}"},
    )

    result = await list_zip_contents(url)

    assert result["total_size_bytes"] == total
    assert result["total_entries"] == 2
    members = {m["name"]: m for m in result["members"]}
    assert members["data.csv"]["uncompressed_size"] == len(b"a,b\n1,2\n")
    assert members["data.csv"]["is_dir"] is False
    assert members["readme.txt"]["uncompressed_size"] == len(b"hello world")


async def test_list_zip_contents_fetches_central_directory_separately_when_outside_tail(
    httpx_mock, monkeypatch
):
    # Force a tiny tail window so the central directory (which precedes the
    # EOCD record) falls outside the first Range fetch, exercising the
    # second Range request for the central directory itself.
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr(csv_reader_module, "_EOCD_TAIL_BYTES", 30)

    zip_bytes = _make_zip({"data.csv": b"a,b\n1,2\n", "readme.txt": b"hello world"})
    total = len(zip_bytes)
    tail = zip_bytes[-30:]
    cd_offset, cd_size, _entries = _parse_eocd(tail)
    url = "https://example.com/tiny-tail.zip"

    httpx_mock.add_response(
        url=url,
        method="GET",
        match_headers={"Range": "bytes=-30"},
        status_code=206,
        content=tail,
        headers={"Content-Range": f"bytes {total - 30}-{total - 1}/{total}"},
    )
    httpx_mock.add_response(
        url=url,
        method="GET",
        match_headers={"Range": f"bytes={cd_offset}-{cd_offset + cd_size - 1}"},
        status_code=206,
        content=zip_bytes[cd_offset : cd_offset + cd_size],
        headers={
            "Content-Range": f"bytes {cd_offset}-{cd_offset + cd_size - 1}/{total}"
        },
    )

    result = await list_zip_contents(url)

    assert result["total_entries"] == 2
    assert {m["name"] for m in result["members"]} == {"data.csv", "readme.txt"}


async def test_list_zip_contents_requires_range_support(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    url = "https://example.com/no-range.zip"
    httpx_mock.add_response(url=url, status_code=200, content=b"whatever bytes")

    with pytest.raises(ValueError, match="no soporta HTTP Range"):
        await list_zip_contents(url)


async def test_preview_ods_reads_header_and_rows(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    ods_bytes = _make_ods([["producto", "precio"], ["cacao", "174.77"], ["banano", "12.5"]])
    url = "https://example.com/precios.ods"
    httpx_mock.add_response(url=url, content=ods_bytes)

    result = await preview_ods(url)

    assert result["headers"] == ["producto", "precio"]
    assert result["rows"] == [["cacao", "174.77"], ["banano", "12.5"]]
    assert result["format"] == "ods"
    assert result["sheet"] == "Hoja1"
    assert result["truncated"] is False


async def test_preview_ods_strips_padded_trailing_columns_and_rows(httpx_mock, monkeypatch):
    # Real-world ODS files pad unused grid space with huge repeat counts on
    # trailing empty cells/rows (spreadsheet editors reserve a full grid,
    # e.g. 1000+ columns/rows) -- these must not leak into the preview as
    # bogus empty columns or blank data rows.
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    ods_bytes = _make_ods(
        [["producto", "precio"], ["cacao", "174.77"]],
        pad_columns=1000,
        pad_rows=500,
    )
    url = "https://example.com/padded.ods"
    httpx_mock.add_response(url=url, content=ods_bytes)

    result = await preview_ods(url)

    assert result["headers"] == ["producto", "precio"]
    assert result["rows"] == [["cacao", "174.77"]]


async def test_preview_ods_truncates_at_max_rows(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    rows = [["producto", "precio"]] + [[f"item{i}", str(i)] for i in range(5)]
    ods_bytes = _make_ods(rows)
    url = "https://example.com/muchas_filas.ods"
    httpx_mock.add_response(url=url, content=ods_bytes)

    result = await preview_ods(url, max_rows=3)

    assert result["total_rows_in_preview"] == 3
    assert result["truncated"] is True


async def test_preview_ods_empty_sheet(httpx_mock, monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    ods_bytes = _make_ods([])
    url = "https://example.com/vacio.ods"
    httpx_mock.add_response(url=url, content=ods_bytes)

    result = await preview_ods(url)

    assert result["headers"] == []
    assert result["rows"] == []

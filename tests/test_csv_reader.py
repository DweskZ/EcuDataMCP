import gzip
import io
import socket
import tarfile

from helpers.csv_reader import (
    MAX_DOWNLOAD_BYTES,
    _gunzip_capped,
    download_bytes,
    normalize_eu_decimal_columns,
    preview_targz,
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

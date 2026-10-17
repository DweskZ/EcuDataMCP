"""Regression tests for the 2026-10-16 review fixes to the parsing pipeline.

Covers: parsers run off the event loop with a time bound, Content-Length is
advisory only, a short zip central directory ends the listing cleanly, a
truncated .xls is refused with a clear message, the IEM bulletin list is not
cached when a source failed, the Supercías export download is byte-capped,
and investigate_dataset bounds its Content-Type sniffs.
"""

from __future__ import annotations

import asyncio
import struct

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

import helpers.csv_reader as csv_reader_module
from helpers import bce_iem_client
from helpers import supercias_financials_build as build_script
from helpers.cache import TtlCache
from helpers.csv_reader import (
    _MAX_DECOMPRESSED_BYTES,
    MAX_DOWNLOAD_BYTES,
    _parse_central_directory,
    download_bytes,
    preview_xls,
    run_parser_off_loop,
)
from tools import investigate_dataset as investigate_dataset_module


@pytest.fixture(autouse=True)
def _allow_test_hosts(monkeypatch):
    # The SSRF guard resolves hosts; tests use a fake host, so resolve it to
    # a public address the way the other csv_reader tests do.
    monkeypatch.setattr(
        csv_reader_module,
        "assert_public_url",
        lambda url: None,
        raising=False,
    )
    from helpers import safe_download

    monkeypatch.setattr(safe_download, "assert_public_url", lambda url: None)


# --- run_parser_off_loop ----------------------------------------------------


async def test_run_parser_off_loop_returns_parser_result():
    assert await run_parser_off_loop(lambda a, b: a + b, 2, 3) == 5


async def test_run_parser_off_loop_times_out_with_spanish_message(monkeypatch):
    monkeypatch.setattr(csv_reader_module, "PARSE_TIMEOUT_SECONDS", 0.05)

    def slow() -> None:
        import time

        time.sleep(0.5)

    with pytest.raises(ValueError, match="tardó más de"):
        await run_parser_off_loop(slow)


# --- Content-Length is advisory ----------------------------------------------


async def test_download_ignores_overstated_content_length(httpx_mock):
    body = b"a,b\n1,2\n"
    httpx_mock.add_response(
        url="https://example.org/small.csv",
        content=body,
        headers={"content-length": str(MAX_DOWNLOAD_BYTES * 10)},
    )

    raw, truncated = await download_bytes("https://example.org/small.csv")

    assert raw == body
    assert truncated is False


async def test_download_tolerates_malformed_content_length(httpx_mock):
    httpx_mock.add_response(
        url="https://example.org/odd.csv",
        content=b"x\n",
        headers={"content-length": "not-a-number"},
    )

    raw, truncated = await download_bytes("https://example.org/odd.csv")

    assert raw == b"x\n"
    assert truncated is False


# --- zip central directory bounds -------------------------------------------


def test_parse_central_directory_stops_on_short_entry():
    # A valid signature followed by fewer than the 46 header bytes used to
    # raise struct.error from unpack_from.
    data = b"PK\x01\x02" + b"\x00" * 10

    assert _parse_central_directory(data, expected_entries=3) == []


def test_parse_central_directory_reads_a_complete_entry_then_stops():
    name = b"datos.csv"
    header = struct.pack(
        "<4sHHHHHHIIIHHHHHII",
        b"PK\x01\x02", 20, 20, 0x0800, 8, 0, 0, 0, 10, 20, len(name), 0, 0, 0, 0, 0, 0,
    )
    data = header + name + b"PK\x01\x02" + b"\x00" * 5

    members = _parse_central_directory(data, expected_entries=5)

    assert [m["name"] for m in members] == ["datos.csv"]
    assert members[0]["compression"] == "deflate"


# --- truncated .xls ----------------------------------------------------------


async def test_preview_xls_over_cap_gives_actionable_message(httpx_mock):
    httpx_mock.add_response(
        url="https://example.org/big.xls",
        content=b"\xd0\xcf" * (_MAX_DECOMPRESSED_BYTES // 2 + 8),
    )

    with pytest.raises(ValueError, match=r"supera el límite de 20 MB"):
        await preview_xls("https://example.org/big.xls")


# --- IEM bulletins: no cache after a failed source ----------------------------

_INDEX_HTML = '<a href="m2092062026.html">No. 2092 Junio 2026</a>'


@pytest.fixture
def _iem_caches():
    bce_iem_client._bulletins_cache = TtlCache(ttl_seconds=60)
    bce_iem_client._last_bulletin_failures = []
    yield


async def test_fetch_bulletins_does_not_cache_when_a_source_failed(httpx_mock, _iem_caches):
    httpx_mock.add_response(url=bce_iem_client.IEM_INDEX_URL, html=_INDEX_HTML)
    httpx_mock.add_response(url=bce_iem_client.IEM_LATEST_PUBLICATIONS_URL, status_code=503)
    httpx_mock.add_response(url=bce_iem_client.IEM_ARCHIVE_URL, html="")

    bulletins = await bce_iem_client._fetch_bulletins()

    assert [b["numero"] for b in bulletins] == [2092]
    assert bce_iem_client._bulletins_cache.get("bulletins") is None
    assert bce_iem_client._bulletin_diagnostics(bulletins)["fuentes_fallidas"] == [
        "ultimas_publicaciones"
    ]


async def test_fetch_bulletins_caches_when_all_sources_answered(httpx_mock, _iem_caches):
    httpx_mock.add_response(url=bce_iem_client.IEM_INDEX_URL, html=_INDEX_HTML)
    httpx_mock.add_response(url=bce_iem_client.IEM_LATEST_PUBLICATIONS_URL, html="")
    httpx_mock.add_response(url=bce_iem_client.IEM_ARCHIVE_URL, html="")

    bulletins = await bce_iem_client._fetch_bulletins()

    assert bce_iem_client._bulletins_cache.get("bulletins") == bulletins
    assert bce_iem_client._bulletin_diagnostics(bulletins)["fuentes_fallidas"] == []


# --- Supercías export download cap --------------------------------------------


def test_download_to_rejects_runaway_file(monkeypatch, tmp_path):
    monkeypatch.setattr(build_script, "_MAX_FILE_BYTES", 3 * 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (8 * 1024))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dest = tmp_path / "bi_ranking.csv"

    with pytest.raises(RuntimeError, match="superó"):
        build_script._download_to(client, "bi_ranking.csv", dest, deadline=1e12)


# --- investigate_dataset bounded sniffing --------------------------------------


async def test_investigate_dataset_bounds_content_type_sniffs(monkeypatch):
    from helpers import ckan_client

    resources = [
        # "HTML" with no extension is UNKNOWN to classify_resource_format (an
        # empty format defaults to CSV), so each one needs a Content-Type sniff.
        {"id": f"r{i}", "name": f"archivo {i}", "url": f"https://x/blob/{i}", "format": "HTML"}
        for i in range(60)
    ]
    dataset = {
        "id": "ds1",
        "name": "muchos-blobs",
        "title": "Muchos blobs",
        "resources": resources,
    }

    async def fake_search_datasets(query, rows=1, source="nacional", session=None):
        return {"count": 1, "results": [{"id": "ds1", "name": "muchos-blobs"}]}

    async def fake_get_dataset(dataset_id, source="nacional", session=None):
        return dataset

    sniffed: list[str] = []
    in_flight = 0
    max_in_flight = 0

    async def fake_sniff(url, session=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        sniffed.append(url)
        return "application/octet-stream"

    monkeypatch.setattr(ckan_client, "search_datasets", fake_search_datasets)
    monkeypatch.setattr(ckan_client, "get_dataset", fake_get_dataset)
    monkeypatch.setattr(investigate_dataset_module, "sniff_content_type", fake_sniff)

    mcp = MCPServer("test")
    investigate_dataset_module.register_investigate_dataset_tool(mcp)
    fn = mcp._tool_manager.get_tool("investigate_dataset").fn
    result = await fn(query="blobs", format="json")

    assert result.structured_content["error"] == "sin_recurso_previsualizable"
    assert len(sniffed) == investigate_dataset_module._MAX_SNIFFED_RESOURCES
    assert max_in_flight <= investigate_dataset_module._SNIFF_CONCURRENCY

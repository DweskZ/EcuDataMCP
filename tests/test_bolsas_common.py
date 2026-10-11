import asyncio

import httpx
import pytest

from helpers import bolsas_common

_URL = "https://www.bolsadevaloresguayaquil.com/boletines/historicos/BVG_Acciones.xlsx"


def test_parse_last_modified_returns_iso_utc():
    assert (
        bolsas_common._parse_last_modified("Thu, 08 Oct 2026 20:35:40 GMT")
        == "2026-10-08T20:35:40+00:00"
    )


@pytest.mark.parametrize("value", [None, "", "not a date"])
def test_parse_last_modified_ignores_missing_or_invalid(value):
    assert bolsas_common._parse_last_modified(value) is None


def test_total_size_prefers_content_range_total():
    headers = httpx.Headers({"Content-Range": "bytes 0-0/1433675", "Content-Length": "1"})
    assert bolsas_common._total_size(headers) == 1433675


def test_total_size_falls_back_to_content_length():
    assert bolsas_common._total_size(httpx.Headers({"Content-Length": "2048"})) == 2048
    # A wildcard total ("*") is not a number: fall back, then give up.
    assert bolsas_common._total_size(httpx.Headers({"Content-Range": "bytes 0-0/*"})) is None


@pytest.mark.asyncio
async def test_probe_archivos_reads_range_headers(httpx_mock):
    httpx_mock.add_response(
        url=_URL,
        status_code=206,
        content=b"P",
        headers={
            "Content-Range": "bytes 0-0/1433675",
            "Last-Modified": "Thu, 08 Oct 2026 20:35:40 GMT",
        },
    )
    archivos = [{"url": _URL}]

    await bolsas_common.probe_archivos(archivos)

    assert archivos[0]["tamano_bytes"] == 1433675
    assert archivos[0]["modificado"] == "2026-10-08T20:35:40+00:00"


@pytest.mark.asyncio
async def test_probe_archivos_failure_keeps_file_with_none_fields(httpx_mock):
    ok = _URL.replace("Acciones", "Bonos")
    httpx_mock.add_response(url=_URL, status_code=404)
    httpx_mock.add_response(
        url=ok,
        status_code=206,
        content=b"P",
        headers={"Content-Range": "bytes 0-0/10"},
    )
    archivos = [{"url": _URL}, {"url": ok}]

    await bolsas_common.probe_archivos(archivos)

    assert archivos[0]["modificado"] is None
    assert archivos[0]["tamano_bytes"] is None
    # One failing probe does not affect the others.
    assert archivos[1]["tamano_bytes"] == 10
    assert archivos[1]["modificado"] is None


@pytest.mark.asyncio
async def test_keyed_locks_are_independent_per_key():
    locks = bolsas_common.KeyedLocks()
    assert locks["a"] is locks["a"]
    assert locks["a"] is not locks["b"]

    async with locks["a"]:
        # A held lock on "a" must not block "b".
        await asyncio.wait_for(locks["b"].acquire(), timeout=1)
        locks["b"].release()

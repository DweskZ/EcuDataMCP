import httpx
import pytest

from helpers import http_client
from helpers.cache import TtlCache

URL = "https://fuente.example.test/api"


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    http_client.reset_cooldowns()

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(http_client.asyncio, "sleep", _no_sleep)
    yield
    http_client.reset_cooldowns()


def test_retry_wait_honours_retry_after_and_caps_it():
    def resp(header):
        return httpx.Response(429, headers={"Retry-After": header} if header else {})

    assert http_client.retry_wait(resp("5"), 0) == 5.0
    assert http_client.retry_wait(resp("3600"), 0) == http_client.MAX_RETRY_WAIT
    assert http_client.retry_wait(resp("0"), 0) == 1.0
    assert http_client.retry_wait(resp(None), 2) == 6.0
    assert http_client.retry_wait(resp("no-es-fecha"), 0) == 2.0


@pytest.mark.asyncio
async def test_retries_a_5xx_then_returns_the_good_response(httpx_mock):
    httpx_mock.add_response(url=URL, status_code=503)
    httpx_mock.add_response(url=URL, json={"ok": True})
    async with http_client.new_client(URL) as client:
        resp = await http_client.get_with_retry(client, URL)
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_repeated_429_trips_a_cooldown_that_fails_fast(httpx_mock):
    httpx_mock.add_response(url=URL, status_code=429)
    httpx_mock.add_response(url=URL, status_code=429)
    async with http_client.new_client(URL) as client:
        with pytest.raises(http_client.RateLimitedError):
            await http_client.get_with_retry(client, URL, attempts=2)
        # No third response registered: the cooldown must answer without a request.
        with pytest.raises(http_client.RateLimitedError) as exc:
            await http_client.get_with_retry(client, URL)
    assert exc.value.host == "fuente.example.test"
    assert exc.value.seconds_left > 0


@pytest.mark.asyncio
async def test_last_5xx_is_returned_for_the_caller_to_report(httpx_mock):
    httpx_mock.add_response(url=URL, status_code=500)
    async with http_client.new_client(URL) as client:
        resp = await http_client.get_with_retry(client, URL, attempts=1)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_transport_error_is_re_raised_after_the_last_attempt(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("sin ruta"))
    httpx_mock.add_exception(httpx.ConnectError("sin ruta"))
    async with http_client.new_client(URL) as client:
        with pytest.raises(httpx.ConnectError):
            await http_client.get_with_retry(client, URL, attempts=2)


def test_new_client_uses_the_profile_timeout():
    client = http_client.new_client(URL, profile="lento")
    assert client.timeout.read == http_client.TIMEOUTS["lento"]
    assert client.headers["User-Agent"].startswith("ecuador-mcp/")


def test_disk_cache_survives_a_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("ECUADOR_MCP_DISK_CACHE", "1")
    monkeypatch.setenv("ECUADOR_MCP_DATA_DIR", str(tmp_path))
    TtlCache(ttl_seconds=60, persist="prueba").set(("catalogo", 2026), {"filas": [1, 2]})

    restarted = TtlCache(ttl_seconds=60, persist="prueba")
    assert restarted.get(("catalogo", 2026)) == {"filas": [1, 2]}
    assert (tmp_path / "cache" / "prueba.json").is_file()


def test_disk_cache_skips_values_that_do_not_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("ECUADOR_MCP_DISK_CACHE", "1")
    monkeypatch.setenv("ECUADOR_MCP_DATA_DIR", str(tmp_path))
    cache = TtlCache(ttl_seconds=60, persist="tuplas")
    cache.set("k", (1, 2))
    assert cache.get("k") == (1, 2)
    assert TtlCache(ttl_seconds=60, persist="tuplas").get("k") is None


def test_disk_cache_off_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("ECUADOR_MCP_DATA_DIR", str(tmp_path))
    TtlCache(ttl_seconds=60, persist="apagado").set("k", 1)
    assert not (tmp_path / "cache").exists()

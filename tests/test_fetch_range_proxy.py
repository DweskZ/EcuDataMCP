import httpx
import pytest

from helpers import csv_reader


@pytest.mark.parametrize("proxy_set", [True, False])
async def test_fetch_range_uses_geo_proxy_for_listed_hosts(monkeypatch, proxy_set):
    if proxy_set:
        monkeypatch.setenv("ECUADOR_MCP_GEO_PROXY", "socks5://127.0.0.1:1080")
    else:
        monkeypatch.delenv("ECUADOR_MCP_GEO_PROXY", raising=False)

    seen: dict = {}

    class _Stop(Exception):
        pass

    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        seen.update(kwargs)
        return real_client(*args, **{k: v for k, v in kwargs.items() if k != "proxy"})

    def fake_do_stream(*args, **kwargs):
        raise _Stop

    monkeypatch.setattr(csv_reader.httpx, "AsyncClient", fake_client)
    monkeypatch.setattr(csv_reader, "safe_stream", fake_do_stream)

    with pytest.raises(_Stop):
        await csv_reader._fetch_range(
            "https://www.datosabiertos.gob.ec/a.zip", "bytes=0-0", 1
        )

    expected = "socks5://127.0.0.1:1080" if proxy_set else None
    assert seen.get("proxy") == expected

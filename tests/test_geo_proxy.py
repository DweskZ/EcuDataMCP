import pytest

from helpers.geo_proxy import get_geo_hosts, proxy_for


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ECUADOR_MCP_GEO_PROXY", raising=False)
    monkeypatch.delenv("ECUADOR_MCP_GEO_HOSTS", raising=False)


def test_no_proxy_configured_means_direct():
    assert proxy_for("https://www.datosabiertos.gob.ec/api/3/action/x") is None


def test_listed_host_and_subdomain_use_proxy(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_GEO_PROXY", "socks5://127.0.0.1:1080")
    assert proxy_for("https://www.datosabiertos.gob.ec/a") == "socks5://127.0.0.1:1080"
    assert proxy_for("https://anda.inec.gob.ec/anda5/") == "socks5://127.0.0.1:1080"


def test_unlisted_host_stays_direct(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_GEO_PROXY", "socks5://127.0.0.1:1080")
    assert proxy_for("https://srienlinea.sri.gob.ec/") is None
    assert proxy_for("https://notdatosabiertos.gob.ec/") is None


def test_gob_ec_and_censo_are_listed_without_catching_every_gob_ec_host(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_GEO_PROXY", "socks5://127.0.0.1:1080")
    assert proxy_for("https://www.gob.ec/api/v1/tramites") == "socks5://127.0.0.1:1080"
    assert proxy_for("https://www.censoecuador.gob.ec/data-y-resultados/") == "socks5://127.0.0.1:1080"
    assert proxy_for("https://www.ecuadorencifras.gob.ec/") is None


def test_hosts_override(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_GEO_PROXY", "http://p:3128")
    monkeypatch.setenv("ECUADOR_MCP_GEO_HOSTS", "Example.ec, other.ec")
    assert get_geo_hosts() == ("example.ec", "other.ec")
    assert proxy_for("https://x.example.ec/") == "http://p:3128"
    assert proxy_for("https://www.datosabiertos.gob.ec/") is None

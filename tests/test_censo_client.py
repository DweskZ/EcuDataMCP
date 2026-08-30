import socket

import pytest

from helpers import censo_client

_PAGE_HTML = """
<html><body>
<a href="https://www.ecuadorencifras.gob.ec/documentos/web-inec/bd-censo/cantonal/BDD_CPV2022_CANT_CSV.zip">canton csv</a>
<a href="https://www.ecuadorencifras.gob.ec/documentos/web-inec/dicc-censo/2022/DICCIONARIO_BDD_CANTON.xlsx">dict</a>
<a href="https://www.censoecuador.gob.ec/wp-content/uploads/2024/12/METODOLOGIA_CPV_2022.pdf">metodologia</a>
<a href="https://www.censoecuador.gob.ec/informacion-geografica/">not a file</a>
</body></html>
"""


def _fake_dns(monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


@pytest.fixture(autouse=True)
def clear_cache():
    censo_client._resources_cache.clear()
    yield
    censo_client._resources_cache.clear()


async def test_search_censo_recursos_parses_files_despite_404_status(
    httpx_mock, monkeypatch
):
    # The real page returns HTTP 404 (a WordPress/Elementor bug) while
    # serving real content -- confirmed live, must not be treated as an error.
    _fake_dns(monkeypatch)
    httpx_mock.add_response(
        url=censo_client.RESULTADOS_URL, status_code=404, html=_PAGE_HTML
    )

    result = await censo_client.search_censo_recursos()

    assert result["total_recursos"] == 3
    urls = [r["url"] for r in result["recursos"]]
    assert (
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/bd-censo/"
        "cantonal/BDD_CPV2022_CANT_CSV.zip" in urls
    )
    assert "https://www.censoecuador.gob.ec/informacion-geografica/" not in urls


async def test_search_censo_recursos_filters_by_query(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    httpx_mock.add_response(
        url=censo_client.RESULTADOS_URL, status_code=404, html=_PAGE_HTML
    )

    result = await censo_client.search_censo_recursos(query="diccionario")

    assert result["total"] == 1
    assert result["recursos"][0]["format"] == "XLSX"


async def test_search_censo_recursos_caches_across_calls(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    httpx_mock.add_response(
        url=censo_client.RESULTADOS_URL, status_code=404, html=_PAGE_HTML
    )

    await censo_client.search_censo_recursos()
    # A second call must not trigger a second HTTP request -- httpx_mock
    # raises if a request has no matching registered response left.
    await censo_client.search_censo_recursos()


async def test_search_censo_recursos_raises_when_page_has_no_files(
    httpx_mock, monkeypatch
):
    _fake_dns(monkeypatch)
    httpx_mock.add_response(
        url=censo_client.RESULTADOS_URL,
        status_code=404,
        html="<html><body>no files here</body></html>",
    )

    with pytest.raises(ValueError, match="No se encontraron archivos"):
        await censo_client.search_censo_recursos()

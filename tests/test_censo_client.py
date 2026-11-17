import socket

import pytest

from helpers import censo_client

# Trimmed from the live /resultados-censo/ page (Elementor markup): the tabulados
# tabs read "Name – [Formato Excel] y [Formato CSV]" under a Población/Vivienda/
# Hogar heading; the databases and dictionaries follow with bare format links.
_RESULTADOS_HTML = """
<html><body>
<nav><a href="https://www.censoecuador.gob.ec/contactanos/">Contáctanos</a></nav>
<h2>Tabulados</h2>
<ul><li>Población</li><li>Vivienda</li><li>Hogar</li></ul>
<div><h3>Población</h3>
<p>Estructura poblacional –
<a href="https://www.censoecuador.gob.ec/wp-content/uploads/2024/04/01_2022_CPV_Estructura_poblacional.xlsx">Formato Excel</a>
y <a href="https://www.censoecuador.gob.ec/wp-content/uploads/2024/04/01_2022_CPV_Estructura_poblacional_CSV.zip">Formato CSV</a></p></div>
<div><h3>Hogar</h3>
<p>Uso de las Tecnologías de la Información y Comunicación –
<a href="https://www.censoecuador.gob.ec/wp-content/uploads/2023/12/03_2022_CPV_TIC.xlsx">Formato Excel</a>
y <a href="https://www.censoecuador.gob.ec/wp-content/uploads/2023/12/03_2022_CPV_TIC.zip">Formato CSV</a></p></div>
<h3>Cantón</h3>
<a href="https://www.ecuadorencifras.gob.ec/documentos/web-inec/bd-censo/cantonal/BDD_CPV2022_CANT_CSV.zip">CSV</a>
<a href="https://www.ecuadorencifras.gob.ec/documentos/web-inec/bd-censo/cantonal/2022_CPV_CANTON_REDATAM.zip">Redatam</a>
<a href="https://www.ecuadorencifras.gob.ec/documentos/web-inec/dicc-censo/2022/DICCIONARIO_BDD_CANTON.xlsx">Cantón</a>
<a href="http://www.censoecuador.gob.ec/wp-content/uploads/2024/03/CPV_2022_Reporte_Tecnico_mar2024.pdf">Reporte Censal</a>
<a href="https://www.censoecuador.gob.ec/informacion-geografica/">not a file</a>
<script>var x = "https://www.censoecuador.gob.ec/wp-content/uploads/ignored.pdf";</script>
</body></html>
"""

_DATA_HTML = """
<html><body>
<a href="http://www.censoecuador.gob.ec/wp-content/uploads/2024/03/CPV_2022_Reporte_Tecnico_mar2024.pdf">Reporte Censal</a>
<a href="https://www.ecuadorencifras.gob.ec/documentos/web-inec/bd-censo/5.GUIA_BASE_CPV_2022_v6.pdf">Guía de Usuario</a>
<a href="https://www.censoecuador.gob.ec/public/BBD_CPV_2010_NACIONAL_CON_CORRESP_2022_SPSS.zip">2010</a>
</body></html>
"""


def _fake_dns(monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


def _mock_pages(httpx_mock, monkeypatch, resultados=_RESULTADOS_HTML, data=_DATA_HTML):
    _fake_dns(monkeypatch)
    httpx_mock.add_response(url=censo_client.RESULTADOS_URL, html=resultados)
    httpx_mock.add_response(url=censo_client.DATA_URL, html=data)


@pytest.fixture(autouse=True)
def clear_cache():
    censo_client._resources_cache.clear()
    yield
    censo_client._resources_cache.clear()


def test_parse_page_labels_tabulados_from_the_text_before_the_links():
    entries = {e["url"].rsplit("/", 1)[-1]: e for e in censo_client.parse_page(_RESULTADOS_HTML)}

    tic = entries["03_2022_CPV_TIC.xlsx"]
    assert tic["label"] == "Uso de las Tecnologías de la Información y Comunicación – Excel"
    assert (tic["tipo"], tic["tema"], tic["format"]) == ("tabulado", "hogar", "XLSX")
    assert entries["03_2022_CPV_TIC.zip"]["label"].endswith("– CSV")
    assert entries["01_2022_CPV_Estructura_poblacional.xlsx"]["tema"] == "poblacion"


def test_parse_page_classifies_microdata_dictionaries_and_documents():
    entries = {e["url"].rsplit("/", 1)[-1]: e for e in censo_client.parse_page(_RESULTADOS_HTML)}

    csv = entries["BDD_CPV2022_CANT_CSV.zip"]
    assert csv["label"] == "Base de datos CPV 2022 – Cantón – CSV"
    assert csv["tipo"] == "microdatos"
    assert entries["2022_CPV_CANTON_REDATAM.zip"]["label"].endswith("Cantón – REDATAM")
    assert entries["DICCIONARIO_BDD_CANTON.xlsx"]["tipo"] == "diccionario"
    # http:// links are upgraded to https so the same file is not listed twice.
    assert (
        entries["CPV_2022_Reporte_Tecnico_mar2024.pdf"]["url"]
        == "https://www.censoecuador.gob.ec/wp-content/uploads/2024/03/CPV_2022_Reporte_Tecnico_mar2024.pdf"
    )
    assert all("ignored.pdf" not in e["url"] for e in entries.values())
    assert not any(u.endswith("informacion-geografica/") for u in entries)


async def test_search_merges_both_pages_without_duplicates(httpx_mock, monkeypatch):
    _mock_pages(httpx_mock, monkeypatch)

    result = await censo_client.search_censo_recursos(limit=100)

    urls = [r["url"] for r in result["recursos"]]
    assert len(urls) == len(set(urls)) == result["total_recursos"] == 10
    guide = next(r for r in result["recursos"] if r["url"].endswith("GUIA_BASE_CPV_2022_v6.pdf"))
    assert guide["tipo"] == "documento"  # a PDF under bd-censo/ is not a database
    nacional = next(r for r in result["recursos"] if "NACIONAL" in r["url"])
    assert nacional["anio"] == "2010" and "recodificado" in nacional["label"]


async def test_search_finds_the_household_ict_tabulado_by_internet(httpx_mock, monkeypatch):
    _mock_pages(httpx_mock, monkeypatch)

    result = await censo_client.search_censo_recursos(query="Internet")

    assert result["total"] == 2
    assert {r["format"] for r in result["recursos"]} == {"XLSX", "ZIP"}
    assert "cantón" in result["recursos"][0]["contenido"]


async def test_search_requires_every_word_and_ignores_accents(httpx_mock, monkeypatch):
    _mock_pages(httpx_mock, monkeypatch)

    assert (await censo_client.search_censo_recursos(query="tabulado hogar"))["total"] == 2
    assert (await censo_client.search_censo_recursos(query="diccionario canton"))["total"] == 1
    assert (await censo_client.search_censo_recursos(query="spss 2010"))["total"] == 1
    assert (await censo_client.search_censo_recursos(query="tabulado nope"))["total"] == 0


async def test_search_caches_across_calls(httpx_mock, monkeypatch):
    _mock_pages(httpx_mock, monkeypatch)

    await censo_client.search_censo_recursos()
    # No second round of requests: httpx_mock fails on an unmatched request.
    await censo_client.search_censo_recursos(query="tic")


async def test_search_raises_when_pages_have_no_files(httpx_mock, monkeypatch):
    html = "<html><body>no files here</body></html>"
    _mock_pages(httpx_mock, monkeypatch, resultados=html, data=html)

    with pytest.raises(ValueError, match="No se encontraron archivos"):
        await censo_client.search_censo_recursos()


async def test_a_404_is_an_error_not_a_page_of_results(httpx_mock, monkeypatch):
    # The retired /data-y-resultados/ URL answered 404 with the site chrome;
    # tolerating that status is what hid every tabulado.
    _fake_dns(monkeypatch)
    httpx_mock.add_response(
        url=censo_client.RESULTADOS_URL, status_code=404, html=_RESULTADOS_HTML
    )

    with pytest.raises(ValueError, match="HTTP 404"):
        await censo_client.search_censo_recursos()


async def test_search_raises_distinct_error_on_403(httpx_mock, monkeypatch):
    # A 403 (seen from some networks, e.g. GitHub Actions' US runners) is a
    # geo/bot block and must not become the generic "no files found".
    _fake_dns(monkeypatch)
    httpx_mock.add_response(
        url=censo_client.RESULTADOS_URL,
        status_code=403,
        html="<html><body>Forbidden</body></html>",
    )

    with pytest.raises(ValueError, match="bloqueo geográfico"):
        await censo_client.search_censo_recursos()

import pytest

from helpers import sri_client

_DATASETS_HTML = """
<html><body>
<p><a href="https://www.sri.gob.ec/files/SRI_Recaudacion_2026.csv">SRI_Recaudación_2026</a> - 7,8 Mb</p>
</body></html>
"""

_ESTADISTICAS_HTML = """
<html><body>
<a href="https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/30ceb557-fc2c-4093-a541-71a80a248d12/Estad%c3%adsticas%20de%20Recaudaci%c3%b3n_julio2026.xlsx">
  <img src="icon.png" /> Ver estadísticas de recaudación
</a>
<a href="https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/30ceb557-fc2c-4093-a541-71a80a248d12/Estad%c3%adsticas%20de%20Recaudaci%c3%b3n_julio2026.xlsx">Ver estadísticas de recaudación</a>
<a href="https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/10922507-2052-41d7-9b04-1f3f699655a8/Recaudaci%c3%b3n%20por%20impuesto%20provincia%20y%20cant%c3%b3n_julio2026.xlsx">Ver recaudación por impuesto, provincia y cantón</a>
<a href="https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/f36d5ff6-f4fd-42b6-85c3-96b62ce1a3c2/Fichas%20y%20serie%20historica%20de%20indicadores_2025.zip">Fichas y serie histórica de indicadores</a>
<a href="https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/b8d41f9b-dffb-4c97-946f-a1fcc1172e98/Bolet%c3%adn%20T%c3%a9cnico%20Anual_2025.pdf">Informe anual (boletín técnico)</a>
</body></html>
"""


@pytest.fixture(autouse=True)
def clear_caches():
    sri_client._files_cache.clear()
    sri_client._estadisticas_cache.clear()
    yield
    sri_client._files_cache.clear()
    sri_client._estadisticas_cache.clear()


@pytest.mark.asyncio
async def test_search_files_finds_dataset_links(httpx_mock):
    httpx_mock.add_response(url=sri_client.SRI_DATASETS_URL, html=_DATASETS_HTML)

    result = await sri_client.search_files()

    assert result["total"] == 1
    assert result["archivos"][0]["format"] == "CSV"
    assert result["archivos"][0]["url"].endswith("SRI_Recaudacion_2026.csv")


@pytest.mark.asyncio
async def test_search_estadisticas_recaudacion_parses_alfresco_links(httpx_mock):
    httpx_mock.add_response(url=sri_client.SRI_ESTADISTICAS_URL, html=_ESTADISTICAS_HTML)

    result = await sri_client.search_estadisticas_recaudacion()

    # The duplicated href (image + text anchor to the same file) is deduped.
    assert result["total_en_pagina"] == 4
    labels = {f["label"]: f["format"] for f in result["archivos"]}
    assert "Estadísticas de Recaudación julio2026" in labels
    assert labels["Estadísticas de Recaudación julio2026"] == "XLSX"
    assert "Fichas y serie historica de indicadores 2025" in labels
    assert labels["Fichas y serie historica de indicadores 2025"] == "ZIP"
    assert "Boletín Técnico Anual 2025" in labels
    assert labels["Boletín Técnico Anual 2025"] == "PDF"


@pytest.mark.asyncio
async def test_search_estadisticas_recaudacion_filters_by_query(httpx_mock):
    httpx_mock.add_response(url=sri_client.SRI_ESTADISTICAS_URL, html=_ESTADISTICAS_HTML)

    result = await sri_client.search_estadisticas_recaudacion(query="impuesto")

    assert result["total"] == 1
    assert "impuesto" in result["archivos"][0]["label"].lower()


@pytest.mark.asyncio
async def test_search_estadisticas_recaudacion_query_is_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=sri_client.SRI_ESTADISTICAS_URL, html=_ESTADISTICAS_HTML)

    result = await sri_client.search_estadisticas_recaudacion(query="boletin tecnico")

    assert result["total"] == 1
    assert result["archivos"][0]["format"] == "PDF"

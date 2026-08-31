import pytest

from helpers import bce_remesas_client

_PAGE_HTML = """
<html><body>
<a href="/documentos/Estadisticas/SectorExterno/BalanzaPagos/Remesas/Flujo_de_remesas_de_trabajadores.xlsx">Flujo de remesas</a>
<a href="/documentos/Estadisticas/SectorExterno/BalanzaPagos/Remesas/Serie_hist%C3%B3rica_remesas_de_trabajadores.xlsx">Serie histórica</a>
<a href="/documentos/Estadisticas/SectorExterno/BalanzaPagos/Remesas/BDD_Remesas_de_trabajadores.csv">Base de datos mensual</a>
<a href="/documentos/Estadisticas/SectorExterno/BalanzaPagos/Remesas/BDD_Remesas_de_trabajadores_entidad.csv">Base de datos por entidad</a>
<a href="/documentos/Estadisticas/SectorExterno/BalanzaPagos/Remesas/BDD_Remesas_de_trabajadores_entidad.csv">Base de datos por entidad (duplicado)</a>
<a href="/documentos/Estadisticas/SectorExterno/BalanzaPagos/Remesas/Nota_al_usuario.pdf">Nota metodológica</a>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    bce_remesas_client._files_cache.clear()
    yield
    bce_remesas_client._files_cache.clear()


@pytest.mark.asyncio
async def test_search_archivos_lists_all_files(httpx_mock):
    httpx_mock.add_response(url=bce_remesas_client._PAGE_URL, html=_PAGE_HTML)

    result = await bce_remesas_client.search_archivos()

    # The duplicated href is deduped.
    assert result["total_en_pagina"] == 5
    labels = {f["label"]: f for f in result["archivos"]}
    assert "Flujo de remesas de trabajadores" in labels
    assert labels["Flujo de remesas de trabajadores"]["format"] == "XLSX"
    assert "BDD Remesas de trabajadores entidad" in labels
    assert labels["BDD Remesas de trabajadores entidad"]["url"].endswith(
        "BDD_Remesas_de_trabajadores_entidad.csv"
    )
    assert labels["BDD Remesas de trabajadores entidad"]["url"].startswith(
        "https://contenido.bce.fin.ec/"
    )


@pytest.mark.asyncio
async def test_search_archivos_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=bce_remesas_client._PAGE_URL, html=_PAGE_HTML)

    result = await bce_remesas_client.search_archivos(query="historica")

    assert result["total"] == 1
    assert result["archivos"][0]["format"] == "XLSX"
    assert "hist" in result["archivos"][0]["label"].lower()


@pytest.mark.asyncio
async def test_search_archivos_distinguishes_bdd_from_serie_historica(httpx_mock):
    httpx_mock.add_response(url=bce_remesas_client._PAGE_URL, html=_PAGE_HTML)

    result = await bce_remesas_client.search_archivos(query="bdd")

    labels = {f["label"] for f in result["archivos"]}
    assert labels == {
        "BDD Remesas de trabajadores",
        "BDD Remesas de trabajadores entidad",
    }


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=bce_remesas_client._PAGE_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=bce_remesas_client._PAGE_URL, html=_PAGE_HTML)

    first = await bce_remesas_client.search_archivos()
    assert first["total_en_pagina"] == 0

    second = await bce_remesas_client.search_archivos()
    assert second["total_en_pagina"] == 5

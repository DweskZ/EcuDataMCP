import pytest

from helpers import bce_precios_comex_client

# Real markup fetched live 2026-09-02 from
# https://contenido.bce.fin.ec/indices-de-precios-de-importacion/ (trimmed
# to the relevant widget -- the rest of the page is unrelated Elementor
# chrome bce_precios_comex_client never looks at).
_IMPORTACION_HTML = """
<html><body>
<div class="elementor-widget-container">
					<style>
.bce-download-list{list-style:none;margin:0;padding:0;}
</style>

<ul class="bce-download-list">

    <li>
        <span class="dashicons dashicons-media-spreadsheet" aria-hidden="true"></span>

        <a href="/documentos/informacioneconomica/SectorExterno/IndicesPrecios/indices_precios_importacion.xlsx">
            Indice de Precios de Importación
        </a>
    </li>

</ul>
</div>
</body></html>
"""

# Same shape, from
# https://contenido.bce.fin.ec/indices-de-precios-de-exportacion/.
_EXPORTACION_HTML = """
<html><body>
<div class="elementor-widget-container">
<ul class="bce-download-list">

    <li>
        <span class="dashicons dashicons-media-spreadsheet" aria-hidden="true"></span>

        <a href="/documentos/informacioneconomica/SectorExterno/IndicesPrecios/indices_precios_exportacion.xlsx">
            Indice de Precios de Exportación
        </a>
    </li>

</ul>
</div>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"

_IMPORTACION_URL = bce_precios_comex_client._PAGINAS[0]["url"]
_EXPORTACION_URL = bce_precios_comex_client._PAGINAS[1]["url"]


@pytest.fixture(autouse=True)
def clear_cache():
    bce_precios_comex_client._files_cache.clear()
    yield
    bce_precios_comex_client._files_cache.clear()


@pytest.mark.asyncio
async def test_search_archivos_lists_files_from_both_pages(httpx_mock):
    httpx_mock.add_response(url=_IMPORTACION_URL, html=_IMPORTACION_HTML)
    httpx_mock.add_response(url=_EXPORTACION_URL, html=_EXPORTACION_HTML)

    result = await bce_precios_comex_client.search_archivos()

    assert result["total"] == 2
    assert result["total_en_paginas"] == 2
    labels = {f["label"]: f for f in result["archivos"]}
    assert "Indice de Precios de Importación" in labels
    assert labels["Indice de Precios de Importación"]["format"] == "XLSX"
    assert labels["Indice de Precios de Importación"]["pagina_id"] == (
        "indices-de-precios-de-importacion"
    )
    assert labels["Indice de Precios de Importación"]["url"] == (
        "https://contenido.bce.fin.ec/documentos/informacioneconomica/SectorExterno/"
        "IndicesPrecios/indices_precios_importacion.xlsx"
    )
    assert "Indice de Precios de Exportación" in labels
    assert labels["Indice de Precios de Exportación"]["pagina_id"] == (
        "indices-de-precios-de-exportacion"
    )


@pytest.mark.asyncio
async def test_search_archivos_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=_IMPORTACION_URL, html=_IMPORTACION_HTML)
    httpx_mock.add_response(url=_EXPORTACION_URL, html=_EXPORTACION_HTML)

    result = await bce_precios_comex_client.search_archivos(query="exportacion")

    assert result["total"] == 1
    assert result["archivos"][0]["pagina_id"] == "indices-de-precios-de-exportacion"


@pytest.mark.asyncio
async def test_search_archivos_matches_query_against_page_title(httpx_mock):
    httpx_mock.add_response(url=_IMPORTACION_URL, html=_IMPORTACION_HTML)
    httpx_mock.add_response(url=_EXPORTACION_URL, html=_EXPORTACION_HTML)

    result = await bce_precios_comex_client.search_archivos(query="grupos de productos")

    assert result["total"] == 1
    assert result["archivos"][0]["pagina_id"] == "indices-de-precios-de-exportacion"


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=_IMPORTACION_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=_EXPORTACION_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=_IMPORTACION_URL, html=_IMPORTACION_HTML)
    httpx_mock.add_response(url=_EXPORTACION_URL, html=_EXPORTACION_HTML)

    first = await bce_precios_comex_client.search_archivos()
    assert first["total_en_paginas"] == 0

    second = await bce_precios_comex_client.search_archivos()
    assert second["total_en_paginas"] == 2


@pytest.mark.asyncio
async def test_one_page_failing_still_returns_the_other(httpx_mock):
    httpx_mock.add_exception(url=_IMPORTACION_URL, exception=Exception("boom"))
    httpx_mock.add_response(url=_EXPORTACION_URL, html=_EXPORTACION_HTML)

    result = await bce_precios_comex_client.search_archivos()

    assert result["total_en_paginas"] == 1
    assert result["archivos"][0]["pagina_id"] == "indices-de-precios-de-exportacion"

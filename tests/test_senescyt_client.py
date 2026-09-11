import pytest

from helpers import senescyt_client

# Trimmed from the real live markup
# (siau.senescyt.gob.ec/estadisticas-de-educacion-superior-ciencia-tecnologia-e-innovacion/,
# confirmed 2026-09-10): a WPBakery accordion ("w-tabs") mixing WPDM package
# shortcodes (Size/Last Updated badges + a data-downloadurl gateway link)
# and plain "Descargar" buttons pointing at a same-origin file or a
# Nextcloud share link. One tab nests two different WPDM packages under one
# accordion title; one tab nests two plain links under another.
_PAGE_HTML = """
<html><body>
<div class="w-tabs-sections">

<div class="w-tabs-section" id="a"><button class="w-tabs-section-header"><div class="w-tabs-section-title">Fichas metodológicas</div></button>
<div class="w-tabs-section-content"><div class="wpb_wrapper"><div class='w3eden wpdm_package_shortcode'>
<h3 style="margin: 10px 0;"><a href="https://siau.senescyt.gob.ec/download/fichas-metodologicas/"><strong>Fichas metodológicas</strong></a></h3>
<ul class="list-group list-group-flush mb-3 ml-0">
<li class="list-group-item">Version <span class="badge bg-info text-dark"></span></li>
<li class="list-group-item">Size <span class="badge bg-secondary">3.61 MB</span></li>
<li class="list-group-item">Last Updated <span class="badge bg-light text-dark">25 abril, 2022</span></li>
</ul>
<a class='wpdm-download-link download-on-click btn btn-primary '  rel='nofollow' href='#' data-downloadurl="https://siau.senescyt.gob.ec/download/fichas-metodologicas/?wpdmdl=13104&refresh=abc">Descargar</a>
</div></div></div></div>

<div class="w-tabs-section" id="b"><button class="w-tabs-section-header"><div class="w-tabs-section-title">Reporte de indicadores año 2021</div></button>
<div class="w-tabs-section-content"><div class="wpb_wrapper"><div class='w3eden wpdm_package_shortcode'>
<h3 style="margin: 10px 0;"><a href="https://siau.senescyt.gob.ec/download/productos-intermedios/"><strong>Productos intermedios</strong></a></h3>
<ul class="list-group list-group-flush mb-3 ml-0">
<li class="list-group-item">Size <span class="badge bg-secondary">36.32 MB</span></li>
<li class="list-group-item">Last Updated <span class="badge bg-light text-dark">25 abril, 2022</span></li>
</ul>
<a class='wpdm-download-link download-on-click btn btn-primary '  rel='nofollow' href='#' data-downloadurl="https://siau.senescyt.gob.ec/download/productos-intermedios/?wpdmdl=13105&refresh=def">Descargar</a>
</div><div class='w3eden wpdm_package_shortcode'>
<h3 style="margin: 10px 0;"><a href="https://siau.senescyt.gob.ec/download/reporte-de-indicadores/"><strong>Reporte de indicadores</strong></a></h3>
<ul class="list-group list-group-flush mb-3 ml-0">
<li class="list-group-item">Size <span class="badge bg-secondary">322.50 KB</span></li>
<li class="list-group-item">Last Updated <span class="badge bg-light text-dark">10 mayo, 2022</span></li>
</ul>
<a class='wpdm-download-link download-on-click btn btn-primary '  rel='nofollow' href='#' data-downloadurl="https://siau.senescyt.gob.ec/download/reporte-de-indicadores/?wpdmdl=13106&refresh=ghi">Descargar</a>
</div></div></div></div>

<div class="w-tabs-section" id="c"><button class="w-tabs-section-header"><div class="w-tabs-section-title">Reporte de indicadores año 2024</div></button>
<div class="w-tabs-section-content"><div class="wpb_wrapper">
<div class="w-btn-wrapper align_none"><a class="w-btn us-btn-style_3 us_custom_074082f9" target="_blank" rel="nofollow" href="https://cloud-pro.senescyt.gob.ec/index.php/s/FjESnmBkDksaYRp"><span class="w-btn-label">Primera parte</span></a></div>
<div class="w-btn-wrapper align_none"><a class="w-btn us-btn-style_3 us_custom_074082f9" target="_blank" rel="nofollow" href="https://cloud-pro.senescyt.gob.ec/index.php/s/FJnCgKTBbtF88Yn"><span class="w-btn-label">Segunda parte</span></a></div>
</div></div></div>

<div class="w-tabs-section" id="d"><button class="w-tabs-section-header"><div class="w-tabs-section-title">PND 2024 &#8211; 2025</div></button>
<div class="w-tabs-section-content"><div class="wpb_wrapper">
<div class="w-btn-wrapper align_none"><a class="w-btn us-btn-style_3 us_custom_074082f9" target="_blank" rel="nofollow" href="https://siau.senescyt.gob.ec/wp-content/uploads/2024/07/Reporte-PND_2024.zip"><span class="w-btn-label">Descargar</span></a></div>
</div></div></div>

</div>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    senescyt_client._page_cache.clear()
    yield
    senescyt_client._page_cache.clear()


@pytest.mark.asyncio
async def test_search_estadisticas_lists_all_entries(httpx_mock):
    httpx_mock.add_response(url=senescyt_client._PAGE_URL, html=_PAGE_HTML)

    result = await senescyt_client.search_estadisticas()

    # 1 (Fichas) + 2 (año 2021) + 2 (Primera/Segunda parte) + 1 (PND) = 6
    assert result["total_en_pagina"] == 6
    assert result["total"] == 6
    assert result["url_fuente"] == senescyt_client._PAGE_URL


@pytest.mark.asyncio
async def test_search_estadisticas_distinguishes_wpdm_packages_under_one_tab(httpx_mock):
    httpx_mock.add_response(url=senescyt_client._PAGE_URL, html=_PAGE_HTML)

    result = await senescyt_client.search_estadisticas(query="reporte de indicadores año 2021")

    titulos = {f["titulo"] for f in result["archivos"]}
    assert titulos == {"Productos intermedios", "Reporte de indicadores"}
    for f in result["archivos"]:
        assert f["seccion"] == "Reporte de indicadores año 2021"
        assert f["tipo"] == "wpdm"
        assert f["formato"] == "DESCONOCIDO"


@pytest.mark.asyncio
async def test_search_estadisticas_captures_wpdm_size_and_updated(httpx_mock):
    httpx_mock.add_response(url=senescyt_client._PAGE_URL, html=_PAGE_HTML)

    result = await senescyt_client.search_estadisticas(query="fichas")

    assert result["total"] == 1
    entry = result["archivos"][0]
    assert entry["tamano"] == "3.61 MB"
    assert entry["actualizado"] == "25 abril, 2022"
    assert entry["url"] == (
        "https://siau.senescyt.gob.ec/download/fichas-metodologicas/?wpdmdl=13104&refresh=abc"
    )


@pytest.mark.asyncio
async def test_search_estadisticas_labels_direct_links_by_their_button_text(httpx_mock):
    httpx_mock.add_response(url=senescyt_client._PAGE_URL, html=_PAGE_HTML)

    result = await senescyt_client.search_estadisticas(query="parte")

    titulos = {f["titulo"] for f in result["archivos"]}
    assert titulos == {
        "Reporte de indicadores año 2024 — Primera parte",
        "Reporte de indicadores año 2024 — Segunda parte",
    }
    for f in result["archivos"]:
        assert f["tipo"] == "directo"
        assert f["tamano"] is None


@pytest.mark.asyncio
async def test_search_estadisticas_infers_format_from_extension_on_direct_links(httpx_mock):
    httpx_mock.add_response(url=senescyt_client._PAGE_URL, html=_PAGE_HTML)

    result = await senescyt_client.search_estadisticas(query="pnd")

    assert result["total"] == 1
    entry = result["archivos"][0]
    assert entry["titulo"] == "PND 2024 – 2025"
    assert entry["formato"] == "ZIP"
    assert entry["tipo"] == "directo"


@pytest.mark.asyncio
async def test_search_estadisticas_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=senescyt_client._PAGE_URL, html=_PAGE_HTML)

    result = await senescyt_client.search_estadisticas(query="ano 2024")

    secciones = {f["seccion"] for f in result["archivos"]}
    assert secciones == {"Reporte de indicadores año 2024"}


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=senescyt_client._PAGE_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=senescyt_client._PAGE_URL, html=_PAGE_HTML)

    first = await senescyt_client.search_estadisticas()
    assert first["total_en_pagina"] == 0

    second = await senescyt_client.search_estadisticas()
    assert second["total_en_pagina"] == 6

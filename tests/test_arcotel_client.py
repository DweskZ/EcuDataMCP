import pytest

from helpers import arcotel_client

# Trimmed but structurally faithful excerpt of the real
# https://www.arcotel.gob.ec/reportes-estadisticos-mensuales/ markup
# (confirmed live 2026-09-02): a nested `<ul id="menu-menu_lateral_institucion">`
# sidebar menu, one `<li>` per year opened by the CMS's own broken-but-
# consistent `<a href="http://Junio">YYYY</a>` header, containing a nested
# `<ul>` of direct `.pdf` links.
_MENSUALES_HTML = """
<html><body>
<div id="cssmenu" class="menu-menu_lateral_institucion-container">
<ul class="menu">
<li id="menu-item-19031" class="menu-item has-sub"><a href="http://Junio">2026</a>
<ul class="menu">
<li><a href="https://www.arcotel.gob.ec/wp-content/uploads/2026/04/1.-Enero-2026.pdf"><strong>Enero</strong></a></li>
<li><a href="https://www.arcotel.gob.ec/wp-content/uploads/2026/08/6.-Junio-2026.pdf"><strong>Junio</strong></a></li>
</ul>
</li>
<li id="menu-item-19031" class="menu-item has-sub"><a href="http://Junio">2025</a>
<ul class="menu">
<li><a href="https://www.arcotel.gob.ec/wp-content/uploads/2022/05/Reporte-estadistico-enero-CO.pdf"><strong>Enero</strong></a></li>
</ul>
</li>
</ul>
</div>
</body></html>
"""

# Trimmed but structurally faithful excerpt of the real
# https://www.arcotel.gob.ec/boletines-estadisticos/ markup (confirmed live
# 2026-09-02): same theme/menu shape as the mensuales page, but entries are
# topic-labeled bulletins rather than one-per-month reports.
_BOLETINES_HTML = """
<html><body>
<div id="cssmenu" class="menu-menu_lateral_institucion-container">
<ul id="menu-menu_lateral_institucion" class="menu">
<li id="menu-item-19031" class="menu-item has-sub"><a href="http://Junio">2024</a>
<ul>
<li><a href="https://www.arcotel.gob.ec/wp-content/uploads/2015/01/Boletin-cierre-2024_compressed-1.pdf">Boletín estadístico 2024</a></li>
</ul>
</li>
<li id="menu-item-19031" class="menu-item has-sub"><a href="http://Junio">2015</a>
<ul>
<li><em><a href="http://www.arcotel.gob.ec/wp-content/uploads/2015/11/Roaming-Nacional_BV_V2.pdf" target="_blank" rel="noopener">Roaming-Nacional Automático</a></em></li>
<li><em><a href="http://www.arcotel.gob.ec/wp-content/uploads/2015/01/Portabilidad-Numerica-MOD.pdf">Portabilidad Numérica</a></em></li>
</ul>
</li>
</ul>
</div>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    arcotel_client._mensuales_cache.clear()
    arcotel_client._boletines_cache.clear()
    yield
    arcotel_client._mensuales_cache.clear()
    arcotel_client._boletines_cache.clear()


@pytest.mark.asyncio
async def test_search_reportes_mensuales_lists_all_entries(httpx_mock):
    httpx_mock.add_response(url=arcotel_client._MENSUALES_URL, html=_MENSUALES_HTML)

    result = await arcotel_client.search_reportes_mensuales()

    assert result["total"] == 3
    assert result["total_en_pagina"] == 3
    assert result["source"].startswith("ARCOTEL")
    labels = {f["label"]: f for f in result["archivos"]}
    assert "Junio" in labels
    entry = labels["Junio"]
    assert entry["anio"] == "2026"
    assert entry["format"] == "PDF"
    assert entry["url"] == (
        "https://www.arcotel.gob.ec/wp-content/uploads/2026/08/6.-Junio-2026.pdf"
    )


@pytest.mark.asyncio
async def test_search_reportes_mensuales_assigns_correct_year_per_entry(httpx_mock):
    httpx_mock.add_response(url=arcotel_client._MENSUALES_URL, html=_MENSUALES_HTML)

    result = await arcotel_client.search_reportes_mensuales()

    by_url = {f["url"]: f for f in result["archivos"]}
    entry_2025 = by_url[
        "https://www.arcotel.gob.ec/wp-content/uploads/2022/05/Reporte-estadistico-enero-CO.pdf"
    ]
    assert entry_2025["anio"] == "2025"
    assert entry_2025["label"] == "Enero"


@pytest.mark.asyncio
async def test_search_reportes_mensuales_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=arcotel_client._MENSUALES_URL, html=_MENSUALES_HTML)

    result = await arcotel_client.search_reportes_mensuales(query="2026")

    assert result["total"] == 2
    assert all(f["anio"] == "2026" for f in result["archivos"])


@pytest.mark.asyncio
async def test_search_boletines_lists_all_entries_and_strips_em_tags(httpx_mock):
    httpx_mock.add_response(url=arcotel_client._BOLETINES_URL, html=_BOLETINES_HTML)

    result = await arcotel_client.search_boletines_estadisticos()

    assert result["total"] == 3
    assert result["total_en_pagina"] == 3
    assert result["source"].startswith("ARCOTEL")
    labels = {f["label"] for f in result["archivos"]}
    assert "Roaming-Nacional Automático" in labels
    assert "Portabilidad Numérica" in labels
    # No raw HTML tag from the <em> wrapper should leak into the label.
    assert not any("<em>" in label for label in labels)


@pytest.mark.asyncio
async def test_search_boletines_filters_by_query(httpx_mock):
    httpx_mock.add_response(url=arcotel_client._BOLETINES_URL, html=_BOLETINES_HTML)

    result = await arcotel_client.search_boletines_estadisticos(query="roaming")

    assert result["total"] == 1
    assert result["archivos"][0]["anio"] == "2015"


@pytest.mark.asyncio
async def test_search_boletines_filters_by_year_query(httpx_mock):
    httpx_mock.add_response(url=arcotel_client._BOLETINES_URL, html=_BOLETINES_HTML)

    result = await arcotel_client.search_boletines_estadisticos(query="2024")

    assert result["total"] == 1
    assert result["archivos"][0]["label"] == "Boletín estadístico 2024"


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=arcotel_client._MENSUALES_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=arcotel_client._MENSUALES_URL, html=_MENSUALES_HTML)

    first = await arcotel_client.search_reportes_mensuales()
    assert first["total_en_pagina"] == 0

    second = await arcotel_client.search_reportes_mensuales()
    assert second["total_en_pagina"] == 3


@pytest.mark.asyncio
async def test_mensuales_and_boletines_caches_are_independent(httpx_mock):
    httpx_mock.add_response(url=arcotel_client._MENSUALES_URL, html=_MENSUALES_HTML)
    httpx_mock.add_response(url=arcotel_client._BOLETINES_URL, html=_BOLETINES_HTML)

    mensuales = await arcotel_client.search_reportes_mensuales()
    boletines = await arcotel_client.search_boletines_estadisticos()

    assert mensuales["total_en_pagina"] == 3
    assert boletines["total_en_pagina"] == 3
    assert mensuales["url_fuente"] != boletines["url_fuente"]

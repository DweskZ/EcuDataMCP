import pytest

from helpers import bce_indices_client

_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://contenido.bce.fin.ec/boletin-analitico-del-sector-petrolero-indice/</loc><lastmod>2026-07-30T08:29:22-05:00</lastmod></url>
<url><loc>https://contenido.bce.fin.ec/boletin-monetario-semanal-indices/</loc><lastmod>2026-07-21T09:02:48-05:00</lastmod></url>
<url><loc>https://contenido.bce.fin.ec/memoria-anual-indice/</loc><lastmod>2026-07-30T15:56:18-05:00</lastmod></url>
<url><loc>https://contenido.bce.fin.ec/estadisticas-de-coyuntura/</loc><lastmod>2026-07-20T10:00:00-05:00</lastmod></url>
</urlset>
"""

# Trimmed real shape confirmed live on
# contenido.bce.fin.ec/boletin-analitico-del-sector-petrolero-indice/
# (2026-09-01): note the "active" class only on the current year's panel,
# and the .bce-gi-cardtop inner layout.
_GI_PAGE_HTML = """
<html><body>
<div class="bce-gi-title"><span class="dashicons dashicons-calendar-alt"></span><div><h2>Boletín Analítico del Sector Petrolero</h2><p>desc</p></div></div>
<section class="bce-gi bce-gi-trimestral"><div class="bce-gi-tabs"></div><div class="bce-gi-content">
<div class="bce-gi-panel active" data-year="2026"><div class="bce-gi-panelhead"><span class="bce-gi-pill">2026</span></div><div class="bce-gi-cards">
<article class="bce-gi-card"><a href="/documentos/Estadisticas/Hidrocarburos/ASP202601.pdf" target="_self"><div class="bce-gi-cardtop"><strong>1er. Trimestre 2026</strong><span class="bce-gi-open">Abrir</span></div><div class="bce-gi-tags"><span>PDF</span></div></a></article>
<article class="bce-gi-card"><a href="/documentos/Estadisticas/Hidrocarburos/ASP202602.pdf" target="_self"><div class="bce-gi-cardtop"><strong>2do.Trimestre 2026</strong><span class="bce-gi-open">Abrir</span></div><div class="bce-gi-tags"><span>PDF</span></div></a></article>
</div></div>
<div class="bce-gi-panel" data-year="2016"><div class="bce-gi-panelhead"><span class="bce-gi-pill">2016</span></div><div class="bce-gi-cards">
<article class="bce-gi-card"><a href="/documentos/Estadisticas/Hidrocarburos/ASP201603.pdf" target="_self"><div class="bce-gi-cardtop"><strong>1er. Trimestre 2016</strong><span class="bce-gi-open">Abrir</span></div><div class="bce-gi-tags"><span>PDF</span></div></a></article>
</div></div>
</div></section>
</body></html>
"""

# Trimmed real shape confirmed live on
# contenido.bce.fin.ec/boletin-monetario-semanal-indices/ (2026-09-01): the
# active year's panel has a bare closing `>`, every other year's panel
# carries a trailing `hidden` attribute instead.
_GI_WEEKLY_PAGE_HTML = """
<html><body>
<section class="bce-gi-weekly" aria-label="Boletín Monetario Semanal"><h2 class="bce-gi-weekly-title">Boletín Monetario Semanal</h2>
<main class="bce-gi-weekly-content">
<section class="bce-gi-weekly-panel" data-year="2026" ><div class="bce-gi-weekly-panel-head"><div class="panel-year">2026</div></div><div class="bce-gi-weekly-months">
<div class="bce-gi-weekly-month"><button class="bce-gi-weekly-month-btn" type="button"><span class="month-name">Enero</span></button><div class="bce-gi-weekly-month-panel" hidden><a class="bce-gi-weekly-link" href="/documentos/Estadisticas/SectorMonFin/IMS_910_09012026.pdf" target="_self" data-search="910"><span class="week-nro">Nro. 910</span><span class="week-date">9 de enero de 2026</span></a></div></div>
</div></section>
<section class="bce-gi-weekly-panel" data-year="2019" hidden><div class="bce-gi-weekly-panel-head"><div class="panel-year">2019</div></div><div class="bce-gi-weekly-months">
<div class="bce-gi-weekly-month"><button class="bce-gi-weekly-month-btn" type="button"><span class="month-name">Diciembre</span></button><div class="bce-gi-weekly-month-panel" hidden><a class="bce-gi-weekly-link" href="/documentos/Estadisticas/SectorMonFin/IMS_595_27122019.pdf" target="_self" data-search="595"><span class="week-nro">Nro. 595</span><span class="week-date">27 de diciembre de 2019</span></a></div></div>
</div></section>
</main></section>
</body></html>
"""

# Trimmed real shape confirmed live on contenido.bce.fin.ec/estadisticas-de-cemento-indice/
# (2026-09-01): a "month-card" inner layout, different from cardtop above.
_GI_MONTH_CARD_HTML = """
<html><body>
<div class="bce-gi-title"><div><h2>Estadísticas de Cemento</h2></div></div>
<section class="bce-gi bce-gi-mensual"><div class="bce-gi-content">
<div class="bce-gi-panel active" data-year="2026"><div class="bce-gi-cards">
<article class="bce-gi-card bce-gi-month-card"><a href="/documentos/Estadisticas/SectorReal/Previsiones/IndCoyuntura/Cemento/ec202601.html" target="_self"><div class="bce-gi-month-body"><div class="bce-gi-month-heading"><span class="dashicons dashicons-calendar-alt"></span><strong>Enero</strong></div><p class="bce-gi-month-desc">Estadísticas de Cemento Enero 2026</p></div><div class="bce-gi-month-footer"><div class="bce-gi-tags"><span>HTML</span></div></div></a></article>
</div></div>
</div></section>
</body></html>
"""

_NO_WIDGET_HTML = "<html><body><p>Página sin contenido publicado todavía.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    bce_indices_client.clear_cache()
    yield
    bce_indices_client.clear_cache()


def test_parse_gi_cards_extracts_years_and_periods():
    titulo, cadencia, items = bce_indices_client._parse_gi_cards(_GI_PAGE_HTML)

    assert titulo == "Boletín Analítico del Sector Petrolero"
    assert cadencia == "trimestral"
    assert len(items) == 3
    assert items[0] == {
        "anio": 2026,
        "periodo": "1er. Trimestre 2026",
        "descripcion": None,
        "fecha": None,
        "fecha_texto": None,
        "url": "https://contenido.bce.fin.ec/documentos/Estadisticas/Hidrocarburos/ASP202601.pdf",
        "formato": "PDF",
    }
    assert items[-1]["anio"] == 2016


def test_parse_gi_cards_handles_month_card_layout():
    titulo, cadencia, items = bce_indices_client._parse_gi_cards(_GI_MONTH_CARD_HTML)

    assert titulo == "Estadísticas de Cemento"
    assert cadencia == "mensual"
    assert len(items) == 1
    assert items[0]["periodo"] == "Enero"
    assert items[0]["descripcion"] == "Estadísticas de Cemento Enero 2026"
    assert items[0]["formato"] == "HTML"


def test_parse_gi_weekly_reads_hidden_and_active_year_panels():
    titulo, items = bce_indices_client._parse_gi_weekly(_GI_WEEKLY_PAGE_HTML)

    assert titulo == "Boletín Monetario Semanal"
    assert len(items) == 2
    assert items[0] == {
        "anio": 2026,
        "periodo": "Nro. 910",
        "descripcion": None,
        "fecha": "2026-01-09",
        "fecha_texto": "9 de enero de 2026",
        "url": "https://contenido.bce.fin.ec/documentos/Estadisticas/SectorMonFin/IMS_910_09012026.pdf",
        "formato": "PDF",
    }
    assert items[1]["anio"] == 2019
    assert items[1]["fecha"] == "2019-12-27"


def test_parse_pagina_returns_none_without_a_recognized_widget():
    assert bce_indices_client._parse_pagina("https://x/", _NO_WIDGET_HTML) is None


@pytest.mark.asyncio
async def test_fetch_catalog_discovers_from_sitemap_and_skips_pages_without_widget(
    httpx_mock,
):
    httpx_mock.add_response(url=bce_indices_client._SITEMAP_URL, html=_SITEMAP_XML)
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-analitico-del-sector-petrolero-indice/",
        html=_GI_PAGE_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-monetario-semanal-indices/",
        html=_GI_WEEKLY_PAGE_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/memoria-anual-indice/", html=_NO_WIDGET_HTML
    )

    catalog = await bce_indices_client._fetch_catalog()

    # estadisticas-de-coyuntura/ doesn't match the -indice(s) slug filter, so
    # it's never fetched; memoria-anual-indice/ is fetched but has no widget.
    ids = {e["pagina_id"] for e in catalog}
    assert ids == {
        "boletin-analitico-del-sector-petrolero-indice",
        "boletin-monetario-semanal-indices",
    }
    petroleo = next(e for e in catalog if e["pagina_id"] == "boletin-analitico-del-sector-petrolero-indice")
    assert petroleo["cadencia"] == "trimestral"
    assert petroleo["total_archivos"] == 3
    assert petroleo["rango_anios"] == [2016, 2026]
    assert petroleo["actualizado_sitemap"] == "2026-07-30T08:29:22-05:00"


@pytest.mark.asyncio
async def test_search_indices_filters_and_omits_archivos(httpx_mock):
    httpx_mock.add_response(url=bce_indices_client._SITEMAP_URL, html=_SITEMAP_XML)
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-analitico-del-sector-petrolero-indice/",
        html=_GI_PAGE_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-monetario-semanal-indices/",
        html=_GI_WEEKLY_PAGE_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/memoria-anual-indice/", html=_NO_WIDGET_HTML
    )

    result = await bce_indices_client.search_indices(query="petrolero")

    assert result["total"] == 1
    assert result["total_paginas"] == 2
    entry = result["paginas"][0]
    assert entry["pagina_id"] == "boletin-analitico-del-sector-petrolero-indice"
    assert "archivos" not in entry


@pytest.mark.asyncio
async def test_get_archivo_filters_by_year_and_caps_results(httpx_mock):
    httpx_mock.add_response(url=bce_indices_client._SITEMAP_URL, html=_SITEMAP_XML)
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-analitico-del-sector-petrolero-indice/",
        html=_GI_PAGE_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-monetario-semanal-indices/",
        html=_GI_WEEKLY_PAGE_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/memoria-anual-indice/", html=_NO_WIDGET_HTML
    )

    all_years = await bce_indices_client.get_archivo("boletin-analitico-del-sector-petrolero-indice")
    assert all_years["total_archivos"] == 3
    assert all_years["archivos_mostrados"] == 3
    assert all_years["truncado"] is False

    only_2016 = await bce_indices_client.get_archivo(
        "boletin-analitico-del-sector-petrolero-indice", anio=2016
    )
    assert only_2016["total_archivos"] == 1
    assert only_2016["archivos"][0]["periodo"] == "1er. Trimestre 2016"

    capped = await bce_indices_client.get_archivo(
        "boletin-analitico-del-sector-petrolero-indice", max_archivos=1
    )
    assert capped["archivos_mostrados"] == 1
    assert capped["truncado"] is True


@pytest.mark.asyncio
async def test_get_archivo_raises_for_unknown_pagina_id(httpx_mock):
    httpx_mock.add_response(url=bce_indices_client._SITEMAP_URL, html=_SITEMAP_XML)
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-analitico-del-sector-petrolero-indice/",
        html=_GI_PAGE_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-monetario-semanal-indices/",
        html=_GI_WEEKLY_PAGE_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/memoria-anual-indice/", html=_NO_WIDGET_HTML
    )

    with pytest.raises(ValueError, match="no encontrada"):
        await bce_indices_client.get_archivo("no-existe")


@pytest.mark.asyncio
async def test_empty_catalog_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=bce_indices_client._SITEMAP_URL, html=_SITEMAP_XML)
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-analitico-del-sector-petrolero-indice/",
        html=_NO_WIDGET_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-monetario-semanal-indices/",
        html=_NO_WIDGET_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/memoria-anual-indice/", html=_NO_WIDGET_HTML
    )
    httpx_mock.add_response(url=bce_indices_client._SITEMAP_URL, html=_SITEMAP_XML)
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-analitico-del-sector-petrolero-indice/",
        html=_GI_PAGE_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/boletin-monetario-semanal-indices/",
        html=_GI_WEEKLY_PAGE_HTML,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/memoria-anual-indice/", html=_NO_WIDGET_HTML
    )

    first = await bce_indices_client.search_indices()
    assert first["total_paginas"] == 0

    second = await bce_indices_client.search_indices()
    assert second["total_paginas"] == 2

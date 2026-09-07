import pytest

from helpers import bce_publicaciones_client

# Trimmed real shape confirmed live on contenido.bce.fin.ec/ultimas-publicaciones/
# (2026-09-01): a bce-ultimas-publicaciones shortcode rendering one static
# <table>, no AJAX/pagination.
_PAGE_HTML = """
<html><body>
<section class="bce-ultimas-publicaciones"><div class="tabla-wrap"><table aria-label="Últimas publicaciones"><colgroup><col class="col-fecha"><col class="col-tipo"><col class="col-nombre"><col class="col-nuevo"></colgroup><thead><tr><th>FECHA DE LA PUBLICACIÓN</th><th>TIPO</th><th>PUBLICACIÓN</th><th></th></tr></thead><tbody>
<tr><td class="fecha">1 de septiembre de 2026</td><td class="icono"><span class="dashicons dashicons-media-document file-pdf" title="Documento PDF"></span></td><td class="publicacion"><a class="nombre-publicacion" target="_self" href="/documentos/Estadisticas/SectorMonFin/IMS_943_28082026.pdf">Boletín Monetario Semanal. 28 de Agosto 2026</a></td><td class="nuevo"><span class="dashicons dashicons-minus icono-vacio" aria-hidden="true"></span></td></tr>
<tr><td class="fecha">1 de septiembre de 2026</td><td class="icono"><span class="dashicons dashicons-media-spreadsheet file-xlsx" title="Hoja de cálculo"></span></td><td class="publicacion"><a class="nombre-publicacion" target="_self" href="/documentos/PublicacionesNotas/Catalogo/Coyuntura/s731/BMS_28082026.xlsx">Reporte de Datos Monetarios Semanal. 28 de Agosto 2026</a></td><td class="nuevo"><span class="dashicons dashicons-yes icono-nuevo" aria-hidden="true"></span></td></tr>
<tr><td class="fecha">31 de agosto de 2026</td><td class="icono"><span class="dashicons dashicons-admin-site-alt3 file-web" title="Publicación web"></span></td><td class="publicacion"><a class="nombre-publicacion" target="_self" href="/documentos/PublicacionesNotas/Catalogo/Encuestas/EOE/iee202607.html">Boletín Analítico del Índice de Expectativas de la Economía (IEE). Julio 2026</a></td><td class="nuevo"><span class="dashicons dashicons-minus icono-vacio" aria-hidden="true"></span></td></tr>
<tr><td class="fecha">6 de agosto de 2026</td><td class="icono"><span class="dashicons dashicons-media-spreadsheet file-xlsx" title="Hoja de cálculo"></span></td><td class="publicacion"><a class="nombre-publicacion" target="_self" href="/documentos/PublicacionesNotas/Catalogo/Coyuntura/s731/BMS_31072026.xlsx">Reporte de Datos Monetarios Semanal. 31 de Julio 2026</a></td><td class="nuevo"><span class="dashicons dashicons-minus icono-vacio" aria-hidden="true"></span></td></tr>
</tbody></table></div></section>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    bce_publicaciones_client.clear_cache()
    yield
    bce_publicaciones_client.clear_cache()


@pytest.mark.asyncio
async def test_search_publicaciones_lists_all_and_parses_fields(httpx_mock):
    httpx_mock.add_response(url=bce_publicaciones_client._PAGE_URL, html=_PAGE_HTML)

    result = await bce_publicaciones_client.search_publicaciones()

    assert result["total_en_pagina"] == 4
    first = result["publicaciones"][0]
    assert first["fecha"] == "2026-09-01"
    assert first["fecha_texto"] == "1 de septiembre de 2026"
    assert first["titulo"] == "Boletín Monetario Semanal. 28 de Agosto 2026"
    assert (
        first["url"]
        == "https://contenido.bce.fin.ec/documentos/Estadisticas/SectorMonFin/IMS_943_28082026.pdf"
    )
    assert first["formato"] == "PDF"
    assert first["icono_titulo"] == "Documento PDF"
    assert first["nuevo"] is False

    last = result["publicaciones"][-1]
    assert last["fecha"] == "2026-08-06"
    assert last["formato"] == "XLSX"


@pytest.mark.asyncio
async def test_search_publicaciones_derives_format_from_url_not_icon(httpx_mock):
    # A "Publicación web" row (.html link) must come back as HTML even though
    # its dashicon class differs from the pdf/xlsx rows.
    httpx_mock.add_response(url=bce_publicaciones_client._PAGE_URL, html=_PAGE_HTML)

    result = await bce_publicaciones_client.search_publicaciones()

    web_row = next(p for p in result["publicaciones"] if "IEE" in p["titulo"])
    assert web_row["formato"] == "HTML"


@pytest.mark.asyncio
async def test_search_publicaciones_detects_nuevo_flag(httpx_mock):
    httpx_mock.add_response(url=bce_publicaciones_client._PAGE_URL, html=_PAGE_HTML)

    result = await bce_publicaciones_client.search_publicaciones()

    nuevo_row = next(
        p for p in result["publicaciones"] if "Reporte de Datos Monetarios" in p["titulo"]
        and p["fecha"] == "2026-09-01"
    )
    assert nuevo_row["nuevo"] is True


@pytest.mark.asyncio
async def test_search_publicaciones_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=bce_publicaciones_client._PAGE_URL, html=_PAGE_HTML)

    result = await bce_publicaciones_client.search_publicaciones(query="expectativas")

    assert result["total"] == 1
    assert "IEE" in result["publicaciones"][0]["titulo"]


@pytest.mark.asyncio
async def test_search_publicaciones_filters_by_formato(httpx_mock):
    httpx_mock.add_response(url=bce_publicaciones_client._PAGE_URL, html=_PAGE_HTML)

    result = await bce_publicaciones_client.search_publicaciones(formato="xlsx")

    assert result["total"] == 2
    assert all(p["formato"] == "XLSX" for p in result["publicaciones"])


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=bce_publicaciones_client._PAGE_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=bce_publicaciones_client._PAGE_URL, html=_PAGE_HTML)

    first = await bce_publicaciones_client.search_publicaciones()
    assert first["total_en_pagina"] == 0

    second = await bce_publicaciones_client.search_publicaciones()
    assert second["total_en_pagina"] == 4

import pytest

from helpers import bce_cuentas_nacionales_client

# Real markup fetched live 2026-09-09 from
# https://contenido.bce.fin.ec/cuadros-de-resultados-cuentas-nacionales-anuales/
# (trimmed to the relevant `#section_cuadros_cna` widget -- the surrounding
# page is unrelated Elementor/Astra chrome the client never looks at).
_CNA_HTML = """
<html><body>
<section class="content" id="section_cuadros_cna">
  <section class="cna-card" aria-labelledby="cna-informes-title">
    <h2 id="cna-informes-title" class="cna-card-title">Informes de resultados</h2>
    <ul class="cna-report-list">
      <li><a class="cna-link" href="/documentos/informacioneconomica/cuentasnacionales/anuales/Informe_resultados_TOU_2023.pdf"><span class="cna-icon cna-icon-pdf"><span class="dashicons dashicons-media-document"></span></span><span>Informe de resultados Cuentas Nacionales Anuales TOU 2023</span></a></li>
    </ul>
  </section>
  <section class="cna-card" aria-labelledby="cna-resultados-title">
    <h2 id="cna-resultados-title" class="cna-card-title">Cuadros de resultados</h2>
    <section id="cna-panel-2024" class="cna-panel is-active" role="tabpanel">
      <ul class="cna-file-list">
        <li><a class="cna-link" href="/documentos/informacioneconomica/cuentasnacionales/anuales/retropolacion_1965_2024p.xlsx"><span class="cna-icon cna-icon-xlsx"><span class="dashicons dashicons-media-spreadsheet"></span></span><span>Serie Hist&oacute;rica y PIB Per C&aacute;pita</span></a></li>
      </ul>
    </section>
  </section>
</section>
</body></html>
"""

# Real markup fetched live 2026-09-09 from
# https://contenido.bce.fin.ec/matriz-de-empleo-e-ingresos-mei/ -- a much
# simpler page than the tabbed CNA widget above: plain <a> links in a
# `.card-body`, no `cna-*` classes at all. Confirms the parser works on
# href/extension structure alone, not on any shared widget CSS.
_MEI_HTML = """
<html><body>
<section class="content" id="section_matriz_mei">
<div class="card"><div class="card-body">
<h5 class="card-title">Descripci&oacute;n</h5>
<p>La Matriz de Empleo e Ingresos permite analizar la relaci&oacute;n entre empleo e ingresos.</p>
<a href="/documentos/informacioneconomica/cuentasnacionales/anuales/mcn_mei_2018_2024p.xlsx">
<span class="dashicons dashicons-media-spreadsheet icon-xlsx"></span>
<span>Descargar serie MEI (2018 - 2024p)</span>
</a>
</div></div>
</section>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"

_CNA_PAGE = {
    "pagina_id": "cuadros-de-resultados-cuentas-nacionales-anuales",
    "titulo": "Cuentas Nacionales Anuales — Cuadros de Resultados",
    "categoria": "anual",
}
_MEI_PAGE = {
    "pagina_id": "matriz-de-empleo-e-ingresos-mei",
    "titulo": "Matriz de Empleo e Ingresos (MEI)",
    "categoria": "anual",
}
_CNA_URL = f"{bce_cuentas_nacionales_client._BASE}/{_CNA_PAGE['pagina_id']}/"
_MEI_URL = f"{bce_cuentas_nacionales_client._BASE}/{_MEI_PAGE['pagina_id']}/"


@pytest.fixture(autouse=True)
def small_catalog(monkeypatch):
    monkeypatch.setattr(
        bce_cuentas_nacionales_client, "_PAGINAS", (_CNA_PAGE, _MEI_PAGE)
    )
    bce_cuentas_nacionales_client._catalog_cache.clear()
    yield
    bce_cuentas_nacionales_client._catalog_cache.clear()


@pytest.mark.asyncio
async def test_search_lists_both_pages_with_file_counts(httpx_mock):
    httpx_mock.add_response(url=_CNA_URL, html=_CNA_HTML)
    httpx_mock.add_response(url=_MEI_URL, html=_MEI_HTML)

    result = await bce_cuentas_nacionales_client.search_cuentas_nacionales()

    assert result["total"] == 2
    assert result["total_paginas"] == 2
    by_id = {p["pagina_id"]: p for p in result["paginas"]}
    assert (
        by_id["cuadros-de-resultados-cuentas-nacionales-anuales"]["total_archivos"] == 2
    )
    assert by_id["matriz-de-empleo-e-ingresos-mei"]["total_archivos"] == 1
    # Summaries never carry the file list itself.
    assert "archivos" not in by_id["matriz-de-empleo-e-ingresos-mei"]


@pytest.mark.asyncio
async def test_search_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=_CNA_URL, html=_CNA_HTML)
    httpx_mock.add_response(url=_MEI_URL, html=_MEI_HTML)

    result = await bce_cuentas_nacionales_client.search_cuentas_nacionales(
        query="empleo"
    )

    assert result["total"] == 1
    assert result["paginas"][0]["pagina_id"] == "matriz-de-empleo-e-ingresos-mei"


@pytest.mark.asyncio
async def test_get_archivo_extracts_labels_and_decodes_entities(httpx_mock):
    httpx_mock.add_response(url=_CNA_URL, html=_CNA_HTML)
    httpx_mock.add_response(url=_MEI_URL, html=_MEI_HTML)

    result = await bce_cuentas_nacionales_client.get_archivo(
        "cuadros-de-resultados-cuentas-nacionales-anuales"
    )

    assert result["total_archivos"] == 2
    labels = {a["label"]: a for a in result["archivos"]}
    assert "Informe de resultados Cuentas Nacionales Anuales TOU 2023" in labels
    assert (
        labels["Informe de resultados Cuentas Nacionales Anuales TOU 2023"]["format"]
        == "PDF"
    )
    # HTML entities (&oacute;/&aacute;) must be decoded, not left literal.
    assert "Serie Histórica y PIB Per Cápita" in labels
    assert labels["Serie Histórica y PIB Per Cápita"]["format"] == "XLSX"
    assert labels["Serie Histórica y PIB Per Cápita"]["url"] == (
        "https://contenido.bce.fin.ec/documentos/informacioneconomica/"
        "cuentasnacionales/anuales/retropolacion_1965_2024p.xlsx"
    )


@pytest.mark.asyncio
async def test_get_archivo_unknown_pagina_id_raises(httpx_mock):
    httpx_mock.add_response(url=_CNA_URL, html=_CNA_HTML)
    httpx_mock.add_response(url=_MEI_URL, html=_MEI_HTML)

    with pytest.raises(ValueError, match="no encontrada"):
        await bce_cuentas_nacionales_client.get_archivo("no-existe")


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=_CNA_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=_MEI_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=_CNA_URL, html=_CNA_HTML)
    httpx_mock.add_response(url=_MEI_URL, html=_MEI_HTML)

    first = await bce_cuentas_nacionales_client.search_cuentas_nacionales()
    assert first["total_paginas"] == 2
    assert all(p["total_archivos"] == 0 for p in first["paginas"])

    second = await bce_cuentas_nacionales_client.search_cuentas_nacionales()
    assert sum(p["total_archivos"] for p in second["paginas"]) == 3


@pytest.mark.asyncio
async def test_one_page_failing_still_returns_the_other(httpx_mock):
    httpx_mock.add_exception(url=_CNA_URL, exception=Exception("boom"))
    httpx_mock.add_response(url=_MEI_URL, html=_MEI_HTML)

    result = await bce_cuentas_nacionales_client.search_cuentas_nacionales()

    assert result["total_paginas"] == 1
    assert result["paginas"][0]["pagina_id"] == "matriz-de-empleo-e-ingresos-mei"

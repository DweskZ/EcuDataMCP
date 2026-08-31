import asyncio

import pytest

from helpers import superbancos_client as sb

_WPCP_WIDGET_HTML = """
<div id='ShareoneDrive-23214b114edeaceb9b0ef5e8467f8b10' data-token='23214b114edeaceb9b0ef5e8467f8b10' data-account-id='341c37a6-daa9-4b83-adad-506b00ccb984' data-drive-id='b!Iz-mji9B1EqK1eiAuGWU7x82x3m7uftFja_xK_rSLWY6gLR41EOqTYg222Ho8lwD'></div>
<script>var ShareoneDrive_vars = {"refresh_nonce":"9924993739"};</script>
"""

# Real shape captured live from the widget's own AJAX response: the outer
# entry div's data-name has NO extension, only the download <a>'s data-name
# does -- a real bug (name pulled from the wrong attribute) was caught by
# checking live output, not by these regexes matching successfully.
_WPCP_FILES_HTML = """
<div class='files-container'>
<div class='entry file ' data-id='ID1' data-name='7. BOLETIN BANCOS JULIO 2026'>
<div class='entry-info-name'><a href='https://www.superbancos.gob.ec/estadisticas/portalestudios/wp-admin/admin-ajax.php?action=shareonedrive-download&id=ID1' class='entry_link entry_action_download' title='7. BOLETIN BANCOS JULIO 2026.zip (722 KB)' data-name='7. BOLETIN BANCOS JULIO 2026.zip' data-entry-id='ID1'><span>7. BOLETIN BANCOS JULIO 2026.zip</span></a></div>
<div class='entry-info-modified-date entry-info-metadata'>11 agosto</div><div class='entry-info-size entry-info-metadata'>722 KB</div>
</div>
<div class='entry file ' data-id='ID2' data-name='6. BOLETIN BANCOS JUNIO 2026'>
<div class='entry-info-name'><a href='httpas://w-group.tech/fake/id=ID2' class='entry_link entry_action_download' title='fake' data-name='6. BOLETIN BANCOS JUNIO 2026.zip' data-entry-id='ID2'><span>x</span></a></div>
</div>
</div>
"""

_BOLETINES_HTML = """
<html><body>
<table id="tablepress-3" class="tablepress tablepress-id-3">
<thead>
<tr class="row-1">
	<th colspan="4" class="column-1"><strong>OTROS AÑOS</th>
</tr>
</thead>
<tbody class="row-striping row-hover">
<tr class="row-2">
	<td class="column-1"><a href="https://www.superbancos.gob.ec/estadisticas/portalestudios/wp-content/uploads/sites/4/downloads/2017/10/BOL_FIN_BCOS_2008.zip">Año 2008</a></td><td class="column-2"><a href="https://www.superbancos.gob.ec/estadisticas/portalestudios/wp-content/uploads/sites/4/downloads/2018/03/BOL_FIN_BCOS_2007.zip">Año 2007</a></td>
</tr>
</tbody>
</table>
<table id="tablepress-1" class="tablepress tablepress-id-1">
<tbody class="row-striping row-hover">
<tr class="row-1">
	<td class="column-1"><a href="https://www.superbancos.gob.ec/estadisticas/portalestudios/download/8692/">Notas Técnicas 8</a><p>Corresponde a la información a partir del 31 de mayo 2021</td><td class="column-2"></td>
</tr>
</tbody>
</table>
</body></html>
"""

_HISTORICA_HTML = """
<html><body>
<table id="tablepress-50" class="tablepress">
<thead>
<tr class="row-1">
	<th colspan="5" class="column-1">DATOS BANCA PÚBLICA</th>
</tr>
</thead>
<tbody class="row-striping row-hover">
<tr class="row-2">
	<td class="column-1"><strong>Año 2020</td><td class="column-2"><a href="https://www.superbancos.gob.ec/estadisticas/portalestudios/wp-content/uploads/sites/4/downloads/2020/02/AT_BPU_ene_2020.pdf">Enero</a></td><td class="column-3"><a href="https://www.superbancos.gob.ec/estadisticas/portalestudios/wp-content/uploads/sites/4/downloads/2020/03/AT_BPU_feb_2020.pdf">Febrero</a></td>
</tr>
<tr class="row-3">
	<td class="column-1"></td><td class="column-2"></td><td class="column-3"><a href="https://www.superbancos.gob.ec/estadisticas/portalestudios/wp-content/uploads/sites/4/downloads/2020/09/AT_BPU_jul_2020.pdf">Julio</a></td>
</tr>
</tbody>
</table>
</body></html>
"""

_BROKEN_DOMAIN_HTML = """
<html><body>
<table id="tablepress-57" class="tablepress">
<tbody class="row-striping row-hover">
<tr class="row-1">
	<td colspan="5" class="column-1"><STRONG>CORRESPONSALES NO BANCARIOS (CNB)</td>
</tr>
<tr class="row-2">
	<td class="column-1"><a href="https://www.superbancos.gob.ec/estadisticas/portalestudios/wp-content/uploads/sites/4/downloads/2021/06/SF-corresponsales-abr-21.zip">A Abril 2021</a></td><td class="column-2"><a href="httpas://w-group.tech/sb/portalestudios/wp-content/uploads/sites/4/downloads/2018/01/corresponsales_dic_16.zip">Año 2016</a></td>
</tr>
</tbody>
</table>
</body></html>
"""

_CALENDARIO_HTML = """
<html><body>
<div class="elementor-icon-box-content">
	<h3 class="elementor-icon-box-title">
		<a href="https://www.superbancos.gob.ec/estadisticas/portalestudios/download/9817/" >
			Calendario Estadístico 2026						</a>
	</h3>
</div>
<h2 class="eael-feature-list-title"><a href="https://www.superbancos.gob.ec/estadisticas/portalestudios/download/8970/" target="_blank">Calendario Estadístico 2025</a></h2>
<h2 class="eael-feature-list-title"><a href="https://www.superbancos.gob.ec/estadisticas/portalestudios/informacion-historica/">Información Histórica</a></h2>
</body></html>
"""


@pytest.fixture(autouse=True)
def clear_cache():
    sb._files_cache.clear()
    yield
    sb._files_cache.clear()


def test_list_secciones_returns_four_fixed_secciones():
    secciones = sb.list_secciones()

    assert len(secciones) == 4
    keys = {s["seccion"] for s in secciones}
    assert keys == {
        "boletines_financieros",
        "servicios_financieros",
        "informacion_historica",
        "calendario_estadistico",
    }
    secciones[0]["seccion"] = "mutated"
    assert sb.list_secciones()[0]["seccion"] != "mutated"


def test_parse_tablepress_handles_thead_colspan_header_and_multiple_tables():
    archivos = sb._parse_tablepress_archivos(_BOLETINES_HTML, "boletines_financieros")

    assert len(archivos) == 3
    assert archivos[0]["grupo"] == "OTROS AÑOS"
    assert archivos[0]["periodo"] is None
    assert archivos[0]["titulo"] == "Año 2008"
    assert archivos[1]["titulo"] == "Año 2007"

    # Second table (no colspan header at all) still parses; grupo carries
    # over from the previous table since nothing resets it -- acceptable,
    # the tool surfaces grupo/periodo/titulo together per entry.
    notas = archivos[2]
    assert notas["titulo"] == "Notas Técnicas 8"
    assert "31 de mayo 2021" in notas["descripcion"]
    assert notas["formato"] == "DESCONOCIDO"


def test_parse_tablepress_splits_periodo_from_titulo_when_year_has_no_link():
    archivos = sb._parse_tablepress_archivos(_HISTORICA_HTML, "informacion_historica")

    # Row 2 has the "Año 2020" label cell plus two month links (Enero,
    # Febrero); row 3 has no "Año" cell of its own (the year was only
    # stated once, in row 2) and one month link (Julio).
    assert len(archivos) == 3
    assert archivos[0]["grupo"] == "DATOS BANCA PÚBLICA"
    assert archivos[0]["periodo"] == "Año 2020"
    assert archivos[0]["titulo"] == "Enero"
    assert archivos[1]["periodo"] == "Año 2020"
    assert archivos[1]["titulo"] == "Febrero"

    # periodo must not leak across rows.
    assert archivos[2]["periodo"] is None
    assert archivos[2]["titulo"] == "Julio"


def test_parse_tablepress_rejects_link_with_unexpected_domain(caplog):
    with caplog.at_level("WARNING"):
        archivos = sb._parse_tablepress_archivos(_BROKEN_DOMAIN_HTML, "servicios_financieros")

    # Only the real superbancos.gob.ec link survives; the mistyped
    # "httpas://w-group.tech/..." link (a real bug found live on the
    # source page) must not be surfaced as a legitimate download.
    assert len(archivos) == 1
    assert archivos[0]["titulo"] == "A Abril 2021"
    assert any("dominio inesperado" in r.message for r in caplog.records)


def test_parse_calendario_matches_both_widget_shapes_and_ignores_other_links():
    archivos = sb._parse_calendario(_CALENDARIO_HTML)

    assert len(archivos) == 2
    titulos = {a["titulo"] for a in archivos}
    assert titulos == {"Calendario Estadístico 2026", "Calendario Estadístico 2025"}


@pytest.mark.asyncio
async def test_get_seccion_archivos(httpx_mock):
    url = sb._SECCIONES_BY_KEY["boletines_financieros"]["url"]
    httpx_mock.add_response(url=url, html=_BOLETINES_HTML)

    result = await sb.get_seccion_archivos("boletines_financieros")

    assert result["seccion"] == "boletines_financieros"
    assert len(result["archivos"]) == 3


@pytest.mark.asyncio
async def test_get_seccion_archivos_rejects_unknown_seccion():
    with pytest.raises(ValueError, match="no reconocida"):
        await sb.get_seccion_archivos("no-existe")


@pytest.mark.asyncio
async def test_calendario_seccion_uses_calendario_parser(httpx_mock):
    url = sb._SECCIONES_BY_KEY["calendario_estadistico"]["url"]
    httpx_mock.add_response(url=url, html=_CALENDARIO_HTML)

    result = await sb.get_seccion_archivos("calendario_estadistico")

    assert len(result["archivos"]) == 2


@pytest.mark.asyncio
async def test_empty_parse_result_is_not_cached(httpx_mock):
    url = sb._SECCIONES_BY_KEY["boletines_financieros"]["url"]
    httpx_mock.add_response(url=url, html="<html><body>Sitio en mantenimiento.</body></html>")
    httpx_mock.add_response(url=url, html=_BOLETINES_HTML)

    first = await sb.get_seccion_archivos("boletines_financieros")
    assert first["archivos"] == []

    second = await sb.get_seccion_archivos("boletines_financieros")
    assert len(second["archivos"]) == 3


@pytest.mark.asyncio
async def test_concurrent_calls_for_same_uncached_seccion_fetch_only_once(httpx_mock):
    url = sb._SECCIONES_BY_KEY["boletines_financieros"]["url"]
    httpx_mock.add_response(url=url, html=_BOLETINES_HTML)

    results = await asyncio.gather(
        sb.get_seccion_archivos("boletines_financieros"),
        sb.get_seccion_archivos("boletines_financieros"),
    )

    assert all(len(r["archivos"]) == 3 for r in results)
    assert len(httpx_mock.get_requests()) == 1


def test_extract_wpcp_params_from_widget_markup():
    params = sb._extract_wpcp_params(_WPCP_WIDGET_HTML)

    assert params == {
        "listtoken": "23214b114edeaceb9b0ef5e8467f8b10",
        "account_id": "341c37a6-daa9-4b83-adad-506b00ccb984",
        "drive_id": "b!Iz-mji9B1EqK1eiAuGWU7x82x3m7uftFja_xK_rSLWY6gLR41EOqTYg222Ho8lwD",
        "nonce": "9924993739",
    }


def test_extract_wpcp_params_returns_none_when_widget_absent():
    assert sb._extract_wpcp_params("<html><body>no widget here</body></html>") is None


def test_parse_wpcp_files_takes_name_from_the_download_link_not_the_outer_div():
    archivos = sb._parse_wpcp_files(_WPCP_FILES_HTML, "boletines_financieros")

    # The second entry's link points at a mistyped/foreign domain and must
    # be dropped, same domain check as the static-table parser.
    assert len(archivos) == 1
    entry = archivos[0]
    # The outer <div data-name='...'> has no extension; only the anchor's
    # own data-name does -- this is exactly the bug that was caught by
    # inspecting real output (format silently came back "DESCONOCIDO" for
    # every entry) rather than by a passing test, until this one existed.
    assert entry["titulo"] == "7. BOLETIN BANCOS JULIO 2026.zip"
    assert entry["formato"] == "ZIP"
    assert entry["tamano"] == "722 KB"
    assert entry["modificado"] == "11 agosto"


def test_parse_wpcp_files_rejects_unexpected_domain(caplog):
    with caplog.at_level("WARNING"):
        archivos = sb._parse_wpcp_files(_WPCP_FILES_HTML, "boletines_financieros")

    assert len(archivos) == 1
    assert any("dominio inesperado" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_wpcp_boletines_recientes_merges_root_files_and_year_folders(httpx_mock):
    root_response = {
        "tree": [
            {"id": "ROOT", "text": "Inicio"},
            {"id": "Y2026", "text": "Año 2026"},
            {"id": "Y2025", "text": "Año 2025"},
        ],
        "html": "<div class='files-container'></div>",
    }
    year_response = {
        "tree": [],
        "html": _WPCP_FILES_HTML,
    }
    ajax_url = sb._WPCP_AJAX_URL
    httpx_mock.add_response(method="POST", url=ajax_url, json=root_response)
    httpx_mock.add_response(method="POST", url=ajax_url, json=year_response)
    httpx_mock.add_response(method="POST", url=ajax_url, json=year_response)

    archivos = await sb._wpcp_boletines_recientes(
        _WPCP_WIDGET_HTML, "https://www.superbancos.gob.ec/estadisticas/portalestudios/bancos/", "boletines_financieros"
    )

    # One real file per year folder (the mistyped-domain entry is dropped
    # in each), no files directly in the root this time.
    assert len(archivos) == 2
    assert {a["grupo"] for a in archivos} == {"Año 2026", "Año 2025"}
    assert all(a["titulo"] == "7. BOLETIN BANCOS JULIO 2026.zip" for a in archivos)


@pytest.mark.asyncio
async def test_wpcp_boletines_recientes_returns_empty_when_no_widget_on_page():
    archivos = await sb._wpcp_boletines_recientes(
        "<html><body>no widget</body></html>",
        "https://www.superbancos.gob.ec/estadisticas/portalestudios/bancos/",
        "boletines_financieros",
    )

    assert archivos == []


@pytest.mark.asyncio
async def test_wpcp_boletines_recientes_degrades_gracefully_when_ajax_call_fails(httpx_mock):
    httpx_mock.add_response(method="POST", url=sb._WPCP_AJAX_URL, status_code=500)

    # Must not raise -- a portal-side failure on the OneDrive call should
    # fall back to "no recent years", not break the whole section.
    archivos = await sb._wpcp_boletines_recientes(
        _WPCP_WIDGET_HTML,
        "https://www.superbancos.gob.ec/estadisticas/portalestudios/bancos/",
        "boletines_financieros",
    )

    assert archivos == []


@pytest.mark.asyncio
async def test_get_seccion_archivos_merges_static_table_and_onedrive_for_boletines(httpx_mock):
    page_html = _BOLETINES_HTML + _WPCP_WIDGET_HTML
    url = sb._SECCIONES_BY_KEY["boletines_financieros"]["url"]
    httpx_mock.add_response(url=url, html=page_html)
    root_response = {"tree": [{"id": "Y2026", "text": "Año 2026"}], "html": ""}
    year_response = {"tree": [], "html": _WPCP_FILES_HTML}
    httpx_mock.add_response(method="POST", url=sb._WPCP_AJAX_URL, json=root_response)
    httpx_mock.add_response(method="POST", url=sb._WPCP_AJAX_URL, json=year_response)

    result = await sb.get_seccion_archivos("boletines_financieros")

    # 3 from the static "OTROS AÑOS"/"Notas Técnicas" tables + 1 real
    # OneDrive entry (the mistyped-domain one is dropped).
    assert len(result["archivos"]) == 4
    assert any(a["grupo"] == "Año 2026" for a in result["archivos"])

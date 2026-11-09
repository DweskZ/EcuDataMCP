"""ANDA access types: the catalog flag vs. what the download page really serves.

Fixtures are trimmed from the live get-microdata pages of catalog 1085 (CPV
2022: flagged "direct" but with only an external link), 1153 (files hosted by
ANDA), 351 (login wall) and 400 (explicit "Data Access Not Available").
"""

import pytest
from mcp.server.mcpserver import MCPServer

from helpers import anda_client
from tools.download_anda_microdata import register_download_anda_microdata_tool
from tools.get_anda_survey_info import register_get_anda_survey_info_tool
from tools.search_anda import register_search_anda_tool

BASE = "https://anda.inec.gob.ec/anda5/index.php"
FORM = '<form><input type="hidden" name="ncsrf" value="abc123def456" /></form>'

# After accepting the terms, CPV 2022 lists ONE resource and it is an external link.
CPV_AFTER_TERMS = """
<div class="resources data-files">
<div class="resource" data-file-type="microdata" >
  <div class="row"><div class="col-md-8 col-lg-9">
    <span class="resource-info" class="resource-info" id="23592">
      <i class="far fa-plus-square icon-expand" aria-hidden="true"></i>
      <i class="far fa-minus-square icon-collapsed" aria-hidden="true"></i>
      Bases de Datos CPV 2022
    </span></div>
    <div class="col-md-4 col-lg-3">
      <a target="_blank" href="https://www.censoecuador.gob.ec/data-censo-ecuador/"
         title="data-censo-ecuador" data-filename="data-censo-ecuador"
         class="download btn btn-outline-primary btn-sm btn-block">
         <i class="fas fa-external-link-square-alt"></i> External link </a>
    </div></div></div></div>
"""

DIRECT_AFTER_TERMS = """
<div class="resource" data-file-type="microdata"><span class="resource-info">Base</span>
<a href="https://anda.inec.gob.ec/anda5/index.php/catalog/1153/download/1" title="enemdu.zip"
   class="download btn">Descargar</a></div>
"""

LOGIN_WALL = """
<h2>Inicie sesión para acceder a los datos</h2>
<a href="/auth/login">Ingresar</a> <a href="/auth/register">Regístrese</a>
"""

NOT_AVAILABLE = "<div class='alert'>Data Access Not Available</div>"

CPV_ROW = {
    "id": "1085",
    "idno": "ECU-INEC-CTIMA-CPV-2022-V1.6",
    "title": "VIII Censo de Población y VII de Vivienda 2022",
    "year_start": "2022",
    "authoring_entity": "INEC",
    "form_model": "direct",
    "url": f"{BASE}/catalog/1085",
}


def _mock_terms_flow(httpx_mock, survey_id, after_terms):
    url = f"{BASE}/catalog/{survey_id}/get-microdata"
    httpx_mock.add_response(method="GET", url=url, html=FORM)
    httpx_mock.add_response(method="POST", url=url, html=after_terms)


def _tool(register, name):
    mcp = MCPServer("test")
    register(mcp)
    return mcp._tool_manager.get_tool(name).fn


def test_parse_external_link_only_is_enlace_externo_not_empty():
    access = anda_client.parse_microdata_page(CPV_AFTER_TERMS)

    assert access["tipo_acceso"] == "enlace_externo"
    assert access["archivos"] == []
    assert access["enlaces_externos"] == [
        {
            "nombre": "Bases de Datos CPV 2022",
            "url": "https://www.censoecuador.gob.ec/data-censo-ecuador/",
        }
    ]


def test_parse_direct_files_win_over_external_links():
    html = DIRECT_AFTER_TERMS + CPV_AFTER_TERMS
    access = anda_client.parse_microdata_page(html)

    assert access["tipo_acceso"] == "directo"
    assert access["archivos"][0]["filename"] == "enemdu.zip"
    assert len(access["enlaces_externos"]) == 1


def test_parse_login_wall_and_not_available_and_unknown_page():
    assert anda_client.parse_microdata_page(LOGIN_WALL)["tipo_acceso"] == "registro"
    assert anda_client.parse_microdata_page(NOT_AVAILABLE)["tipo_acceso"] == "ninguno"
    with pytest.raises(ValueError, match="No se reconoció"):
        anda_client.parse_microdata_page("<html>captcha</html>")


def test_access_summary_falls_back_to_the_catalog_flag():
    assert anda_client.access_summary({"form_model": "data_na"}, None) == {
        "tipo_acceso": "ninguno",
        "microdatos_disponibles": False,
    }
    assert anda_client.access_summary(CPV_ROW, None) == {
        "tipo_acceso": "desconocido",
        "microdatos_disponibles": True,
    }
    assert anda_client.access_summary(CPV_ROW, {"tipo_acceso": "ninguno"}) == {
        "tipo_acceso": "ninguno",
        "microdatos_disponibles": False,
    }


@pytest.mark.asyncio
async def test_get_microdata_access_reads_login_wall_without_the_terms_form(httpx_mock):
    httpx_mock.add_response(
        method="GET", url=f"{BASE}/catalog/351/get-microdata", html=LOGIN_WALL
    )
    assert (await anda_client.get_microdata_access("351"))["tipo_acceso"] == "registro"


@pytest.mark.asyncio
async def test_search_and_download_agree_for_cpv_2022(httpx_mock, monkeypatch):
    """The reported inconsistency: search said microdata, download said 0 files."""
    anda_client._access_cache.clear()
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog?ps=10",
        json={"result": {"found": "1", "rows": [CPV_ROW]}},
    )
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog/1085?id_format=id",
        json={"status": "success", "dataset": {**CPV_ROW, "data_access_type": "direct"}},
    )
    # Search verifies the study once (cached), the download tool fetches it again.
    _mock_terms_flow(httpx_mock, "1085", CPV_AFTER_TERMS)
    _mock_terms_flow(httpx_mock, "1085", CPV_AFTER_TERMS)

    search = _tool(register_search_anda_tool, "search_anda")
    found = (await search(format="json")).structured_content["results"][0]
    download = _tool(register_download_anda_microdata_tool, "download_anda_microdata")
    got = (await download(idno="1085", format="json")).structured_content

    assert found["tipo_acceso"] == got["tipo_acceso"] == "enlace_externo"
    assert found["microdatos_disponibles"] is True
    assert got["total_archivos"] == 0
    assert got["total_enlaces_externos"] == 1
    assert got["enlaces_externos"][0]["url"] == "https://www.censoecuador.gob.ec/data-censo-ecuador/"
    assert "search_archivos" in got["siguiente_paso"]
    anda_client._access_cache.clear()


@pytest.mark.asyncio
async def test_search_marks_a_study_without_any_access_as_unavailable(httpx_mock):
    anda_client._access_cache.clear()
    row = {**CPV_ROW, "id": "400", "title": "IPI 2014"}
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog?ps=10", json={"result": {"found": "1", "rows": [row]}}
    )
    httpx_mock.add_response(
        method="GET", url=f"{BASE}/catalog/400/get-microdata", html=NOT_AVAILABLE
    )

    search = _tool(register_search_anda_tool, "search_anda")
    found = (await search(format="json")).structured_content["results"][0]

    assert found["tipo_acceso"] == "ninguno"
    assert found["microdatos_disponibles"] is False
    anda_client._access_cache.clear()


@pytest.mark.asyncio
async def test_search_degrades_to_the_catalog_flag_when_the_check_fails(httpx_mock):
    anda_client._access_cache.clear()
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog?ps=10", json={"result": {"found": "1", "rows": [CPV_ROW]}}
    )
    httpx_mock.add_response(
        method="GET", url=f"{BASE}/catalog/1085/get-microdata", status_code=503
    )

    search = _tool(register_search_anda_tool, "search_anda")
    found = (await search(format="json")).structured_content["results"][0]

    assert found["tipo_acceso"] == "desconocido"
    assert found["microdatos_disponibles"] is True
    anda_client._access_cache.clear()


@pytest.mark.asyncio
async def test_search_can_skip_the_verification(httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog?ps=10", json={"result": {"found": "1", "rows": [CPV_ROW]}}
    )
    search = _tool(register_search_anda_tool, "search_anda")
    found = (await search(verificar_acceso=False, format="json")).structured_content["results"][0]
    assert found["tipo_acceso"] == "desconocido"


@pytest.mark.asyncio
async def test_download_direct_files_keep_working(httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog/1153?id_format=id",
        json={"status": "success", "dataset": {"id": "1153", "title": "ENEMDU", "data_access_type": "direct"}},
    )
    _mock_terms_flow(httpx_mock, "1153", DIRECT_AFTER_TERMS)

    download = _tool(register_download_anda_microdata_tool, "download_anda_microdata")
    got = (await download(idno="1153", format="json")).structured_content

    assert got["tipo_acceso"] == "directo"
    assert got["total_archivos"] == 1
    assert got["archivos"][0]["url"].endswith("/catalog/1153/download/1")
    assert "siguiente_paso" not in got


@pytest.mark.asyncio
async def test_download_text_lists_external_links(httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog/1085?id_format=id",
        json={"status": "success", "dataset": {**CPV_ROW, "data_access_type": "direct"}},
    )
    _mock_terms_flow(httpx_mock, "1085", CPV_AFTER_TERMS)

    download = _tool(register_download_anda_microdata_tool, "download_anda_microdata")
    result = await download(idno="1085")
    text = result.content[0].text

    assert "tipo_acceso: enlace_externo" in text
    assert "https://www.censoecuador.gob.ec/data-censo-ecuador/" in text
    assert "No se encontraron archivos" not in text


@pytest.mark.asyncio
async def test_survey_info_reports_the_verified_access(httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog/1085?id_format=id",
        json={"status": "success", "dataset": {**CPV_ROW, "data_access_type": "direct"}},
    )
    _mock_terms_flow(httpx_mock, "1085", CPV_AFTER_TERMS)

    info = _tool(register_get_anda_survey_info_tool, "get_anda_survey_info")
    got = (await info(idno="1085", format="json")).structured_content

    assert got["tipo_acceso"] == "enlace_externo"
    assert got["microdatos_disponibles"] is True
    assert got["enlaces_externos"][0]["nombre"] == "Bases de Datos CPV 2022"

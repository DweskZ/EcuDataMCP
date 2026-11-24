import asyncio
import json

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from helpers import anda_materiales
from helpers.anda_materiales import get_related_materials, parse_material_links
from tools import register_tools
from tools.get_anda_materiales import register_get_anda_materiales_tool

PAGE = "https://anda.inec.gob.ec/anda5/index.php/catalog/809/related-materials"
SITE = "https://anda.inec.gob.ec/anda5/"

# Shaped like the real page (catalog 809, checked live 2026-11-24): the visible
# text of every button is only "Descargar [FORMAT, SIZE]"; the file's own name
# is in the link's title and data-filename.
REAL_PAGE = """
<div class="resource">
  <span class="resource-info">1. Serie Historica del IPC</span>
  <div class="resource-action-buttons">
    <a target="_blank" href="https://anda.inec.gob.ec/anda5/index.php/catalog/809/download/16414"
       title="1. Serie Historica del IPC.zip" data-filename="1. Serie Historica del IPC.zip"
       data-dctype="Document, Review"> Descargar [ZIP, 117.14 KB] </a>
  </div>
</div>
<div class="resource">
  <span class="resource-info">6. Serie de índices descriptivos IPC base 2014</span>
  <a target="_blank" href="/anda5/index.php/catalog/809/download/16419"
     title="6. Serie de indices descriptivos IPC base 2014.zip"
     data-filename="6. Serie de indices descriptivos IPC base 2014.zip"> Descargar [ZIP, 474.32 KB] </a>
</div>
<div class="resource">
  <a href="/anda5/index.php/catalog/809/download/16397" title="4. Formulario IPC-1 (Articulos).pdf"
     data-filename="4. Formulario IPC-1 (Articulos).pdf">Descargar [PDF, 61.89 KB]</a>
</div>
<a href="/anda5/index.php/catalog/809/download/16414">Descargar [ZIP, 117.14 KB]</a>
<a href="/anda5/index.php/catalog/999/download/123" title="Otro estudio.zip">Descargar [ZIP, 1 KB]</a>
<a href="https://evil.example/anda5/index.php/catalog/809/download/16420" title="Extraño.zip">Descargar [ZIP, 1 KB]</a>
<a href="/anda5/index.php/catalog/809/get-microdata">Microdatos</a>
"""


def test_names_are_the_files_own_names_not_the_download_button_text():
    result = parse_material_links(REAL_PAGE, PAGE, "809")

    assert [row["nombre"] for row in result] == [
        "1. Serie Historica del IPC.zip",
        "6. Serie de indices descriptivos IPC base 2014.zip",
        "4. Formulario IPC-1 (Articulos).pdf",
    ]
    assert not any("Descargar" in row["nombre"] for row in result)


def test_format_and_size_come_from_the_download_button():
    result = parse_material_links(REAL_PAGE, PAGE, "809")

    assert (result[0]["formato"], result[0]["tamano"]) == ("ZIP", "117.14 KB")
    assert (result[2]["formato"], result[2]["tamano"]) == ("PDF", "61.89 KB")


def test_only_this_catalogs_downloads_on_the_anda_host_are_kept_once():
    urls = [row["url"] for row in parse_material_links(REAL_PAGE, PAGE, "809")]

    assert urls == [
        "https://anda.inec.gob.ec/anda5/index.php/catalog/809/download/16414",
        "https://anda.inec.gob.ec/anda5/index.php/catalog/809/download/16419",
        "https://anda.inec.gob.ec/anda5/index.php/catalog/809/download/16397",
    ]


def test_a_link_with_no_name_attributes_falls_back_to_its_text_then_a_default():
    html = (
        '<a href="/anda5/index.php/catalog/809/download/1">Canasta básica</a>'
        '<a href="/anda5/index.php/catalog/809/download/2"></a>'
    )

    names = [row["nombre"] for row in parse_material_links(html, PAGE, "809")]

    assert names == ["Canasta básica", "Material relacionado"]


def test_the_allowed_host_and_path_follow_the_configured_site_base():
    html = (
        '<a href="https://mirror.example/anda9/index.php/catalog/809/download/7" title="A.zip"></a>'
        '<a href="https://anda.inec.gob.ec/anda5/index.php/catalog/809/download/8" title="B.zip"></a>'
    )

    result = parse_material_links(
        html, "https://mirror.example/anda9/index.php/catalog/809/related-materials", "809",
        site_base="https://mirror.example/anda9/",
    )

    assert [row["nombre"] for row in result] == ["A.zip"]


@pytest.mark.asyncio
async def test_related_materials_requests_the_catalog_page(httpx_mock):
    httpx_mock.add_response(url=PAGE, text=REAL_PAGE)

    result = await get_related_materials("809")

    assert result["total"] == 3
    assert result["url_fuente"] == PAGE
    assert result["archivos"][0]["nombre"] == "1. Serie Historica del IPC.zip"


@pytest.mark.asyncio
async def test_invalid_id_rejected():
    with pytest.raises(ValueError):
        await get_related_materials("../other")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 500])
async def test_an_id_anda_does_not_have_gets_a_clear_message(httpx_mock, status):
    # ANDA answers 500, not 404, for a catalog id it does not have.
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/catalog/99999/related-materials",
        status_code=status,
    )

    with pytest.raises(ValueError, match=f"no devolvió el catálogo 99999 \\(HTTP {status}\\)"):
        await get_related_materials("99999")


@pytest.mark.asyncio
async def test_other_http_errors_are_not_reported_as_a_missing_id(httpx_mock):
    httpx_mock.add_response(url=PAGE, status_code=403)

    with pytest.raises(httpx.HTTPStatusError):
        await get_related_materials("809")


def _server_with_stubbed_helper(monkeypatch) -> MCPServer:
    async def fake(survey_id, session=None):
        return {
            "fuente": "INEC ANDA", "url_fuente": PAGE, "id": survey_id, "total": 1,
            "archivos": [{
                "nombre": "1. Serie Historica del IPC.zip", "formato": "ZIP",
                "tamano": "117.14 KB",
                "url": "https://anda.inec.gob.ec/anda5/index.php/catalog/809/download/16414",
            }],
            "nota": "nota",
        }

    monkeypatch.setattr(anda_materiales, "get_related_materials", fake)
    server = MCPServer("test")
    register_get_anda_materiales_tool(server)
    return server


async def test_tool_text_shows_name_format_size_and_url(monkeypatch):
    server = _server_with_stubbed_helper(monkeypatch)

    text = (await server.call_tool("get_anda_materiales", {"id": "809"})).content[0].text

    assert "Materiales ANDA 809 (1):" in text
    assert (
        "- 1. Serie Historica del IPC.zip [ZIP, 117.14 KB]: "
        "https://anda.inec.gob.ec/anda5/index.php/catalog/809/download/16414"
    ) in text


async def test_tool_json_carries_the_structured_files(monkeypatch):
    server = _server_with_stubbed_helper(monkeypatch)

    result = await server.call_tool("get_anda_materiales", {"id": "809", "format": "json"})
    payload = json.loads(result.content[0].text)

    assert payload["archivos"][0]["formato"] == "ZIP"
    assert payload["total"] == 1


async def test_tool_wraps_a_helper_error_in_a_tool_error(monkeypatch):
    async def failing(survey_id, session=None):
        raise ValueError("el id no existe")

    monkeypatch.setattr(anda_materiales, "get_related_materials", failing)
    server = MCPServer("test")
    register_get_anda_materiales_tool(server)

    with pytest.raises(Exception, match="Error al consultar materiales de ANDA: el id no existe"):
        await server.call_tool("get_anda_materiales", {"id": "1"})


def _registered(monkeypatch, **env) -> set[str]:
    for name in ("ECUADOR_MCP_HIDE_TOOLS", "ECUADOR_MCP_HIDE_GEOBLOCKED", "ECUADOR_MCP_GEO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    server = MCPServer("test")
    register_tools(server)
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_the_tool_is_registered_by_default(monkeypatch):
    assert "get_anda_materiales" in _registered(monkeypatch)


def test_the_tool_is_hidden_with_the_other_geoblocked_anda_tools(monkeypatch):
    names = _registered(monkeypatch, ECUADOR_MCP_HIDE_GEOBLOCKED="1")

    assert "get_anda_materiales" not in names
    assert "search_anda" not in names


def test_the_tool_can_be_hidden_by_name(monkeypatch):
    names = _registered(monkeypatch, ECUADOR_MCP_HIDE_TOOLS="get_anda_materiales")

    assert "get_anda_materiales" not in names
    assert "search_anda" in names

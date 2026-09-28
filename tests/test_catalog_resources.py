import asyncio
import json

from mcp.server.mcpserver import MCPServer

from resources.catalog import _fuentes_payload
from tools import register_maintenance_tools, register_tools


def test_fuentes_lists_every_integrated_source_family():
    payload = _fuentes_payload()
    sources = {source["id"]: source for source in payload["fuentes"]}

    assert {
        "ckan",
        "cuenca",
        "latacunga",
        "sri",
        "gobec",
        "sercop",
        "sgr",
        "igepn",
        "geo",
        "anda",
        "inec-estadisticas",
        "inec-biinec",
        "inec-censo",
        "bce",
        "sipa",
        "contraloria",
        "supercias",
        "supercias-financials",
        "superbancos",
        "cenace",
        "sut",
    } <= sources.keys()
    assert "search_biinec_extras" in sources["inec-biinec"]["tools"]
    assert "get_contraloria_informe" in sources["contraloria"]["tools"]
    assert "get_tramite_estadisticas" in sources["gobec"]["tools"]
    assert "search_informes_igepn" in sources["igepn"]["tools"]
    assert "get_sri_ruc_info" in sources["sri"]["tools"]
    assert "list_bce_indicadores_diarios" in sources["bce"]["tools"]
    assert "get_archivo_seccion" in sources["superbancos"]["tools"]
    assert "get_cenace_tablero" in sources["cenace"]["tools"]
    assert "query_sut_indicador" in sources["sut"]["tools"]
    assert json.loads(json.dumps(payload, ensure_ascii=False))["fuentes"]


def _registered_tool_names() -> set[str]:
    mcp = MCPServer("test")
    register_tools(mcp)
    register_maintenance_tools(mcp)
    return {tool.name for tool in asyncio.run(mcp.list_tools())}


def test_fuentes_covers_every_registered_tool():
    listed = {
        tool for source in _fuentes_payload()["fuentes"] for tool in source["tools"]
    }
    missing = sorted(_registered_tool_names() - listed)
    assert not missing, f"tools missing from ecuador://fuentes: {missing}"


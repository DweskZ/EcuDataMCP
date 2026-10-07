import asyncio
import json

from mcp.server.mcpserver import MCPServer

from helpers.geo_proxy import GEOBLOCKED_TOOLS
from prompts.workflows import register_workflow_prompts
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
    assert "list_catalogo" in sources["bce"]["tools"]
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


def test_hidden_geoblocked_tools_leave_tools_and_catalog(monkeypatch):
    monkeypatch.delenv("ECUADOR_MCP_GEO_PROXY", raising=False)
    monkeypatch.setenv("ECUADOR_MCP_HIDE_GEOBLOCKED", "1")

    registered = _registered_tool_names()
    payload = _fuentes_payload()
    listed = {tool for source in payload["fuentes"] for tool in source["tools"]}
    source_ids = {source["id"] for source in payload["fuentes"]}

    assert not registered & GEOBLOCKED_TOOLS
    assert not listed & GEOBLOCKED_TOOLS
    assert {"anda", "supercias", "supercias-financials"}.isdisjoint(source_ids)
    assert {"search_datasets", "search_contratos", "get_sri_ruc_info"} <= registered
    assert registered - {"audit_bce_catalog", "compare_bce_sources"} <= listed


def test_buscar_inec_prompt_skips_anda_when_hidden(monkeypatch):
    monkeypatch.delenv("ECUADOR_MCP_GEO_PROXY", raising=False)
    mcp = MCPServer("test")
    register_workflow_prompts(mcp)

    monkeypatch.delenv("ECUADOR_MCP_HIDE_GEOBLOCKED", raising=False)
    shown = asyncio.run(mcp.get_prompt("buscar_inec", {"tema": "empleo"}))
    monkeypatch.setenv("ECUADOR_MCP_HIDE_GEOBLOCKED", "1")
    hidden = asyncio.run(mcp.get_prompt("buscar_inec", {"tema": "empleo"}))

    assert "salta el paso 1" not in str(shown)
    assert "salta el paso 1" in str(hidden)


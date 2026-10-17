import asyncio

import pytest
from mcp.server.mcpserver import MCPServer

import tools.search_ecuador as search_ecuador_module
from helpers import ckan_client, gobec_client, sercop_client, sgr_client
from tools.search_ecuador import register_search_ecuador_tool


def _make_tool():
    mcp = MCPServer("test")
    register_search_ecuador_tool(mcp)
    return mcp._tool_manager.get_tool("search_ecuador").fn


@pytest.fixture
def quiet_sources(monkeypatch):
    """Every source answers empty and fast, so a test can slow one down."""

    async def empty_list(*args, **kwargs):
        return []

    async def no_contracts(*args, **kwargs):
        return {"data": [], "total": 0, "_resolved_year": 2026}

    async def no_events(*args, **kwargs):
        return {"events": [], "total": 0}

    async def no_datasets(*args, **kwargs):
        return {"results": [], "count": 0}

    async def no_regulaciones(*args, **kwargs):
        return {"resultados": [], "paginas_leidas": 1, "hay_mas": False}

    monkeypatch.setattr(ckan_client, "search_datasets", no_datasets)
    monkeypatch.setattr(ckan_client, "list_organizations", empty_list)
    monkeypatch.setattr(gobec_client, "search_tramites", empty_list)
    monkeypatch.setattr(gobec_client, "find_regulaciones", no_regulaciones)
    monkeypatch.setattr(sercop_client, "search_contracts", no_contracts)
    monkeypatch.setattr(sgr_client, "list_risk_events", no_events)


async def test_slow_source_times_out_into_its_own_error_section(monkeypatch, quiet_sources):
    # gob.ec can take minutes; one hanging source must not hold the whole
    # unified search, and its section reports the timeout like any error.
    async def hang(*args, **kwargs):
        await asyncio.sleep(5)
        return []

    monkeypatch.setattr(gobec_client, "search_tramites", hang)
    monkeypatch.setattr(search_ecuador_module, "_SOURCE_TIMEOUT_SECONDS", 0.05)

    tool = _make_tool()
    result = await asyncio.wait_for(tool(query="salud", format="json"), timeout=2)
    payload = result.structured_content

    assert payload["tramites"] == {"error": "la fuente no respondió en 0.05 s"}
    assert payload["datasets"] == {"count": 0, "results": []}
    assert payload["regulaciones"] == []


async def test_source_exceptions_still_render_as_section_errors(monkeypatch, quiet_sources):
    async def boom(*args, **kwargs):
        raise RuntimeError("SGR caído")

    monkeypatch.setattr(sgr_client, "list_risk_events", boom)

    tool = _make_tool()
    payload = (await tool(query="sismo", format="json")).structured_content

    assert payload["riesgos"] == {"error": "SGR caído"}
    assert payload["contratos"]["total"] == 0

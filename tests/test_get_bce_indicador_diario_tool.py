import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import bce_indicadores_diarios_client as bce
from tools.get_bce_indicador_diario import register_get_bce_indicador_diario_tool


def _make_tool():
    mcp = MCPServer("test")
    register_get_bce_indicador_diario_tool(mcp)
    return mcp._tool_manager.get_tool("get_bce_indicador_diario").fn


@pytest.fixture(autouse=True)
def clear_cache():
    bce._files_cache.clear()
    yield
    bce._files_cache.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["01/01/2024", "2024-13-01", "2024-1-1", "20240101"])
async def test_rejects_desde_not_in_iso_format(bad):
    tool = _make_tool()

    with pytest.raises(ToolError, match="desde debe tener formato YYYY-MM-DD"):
        await tool("datos_formulario.json", "val_ind_0003", desde=bad)


@pytest.mark.asyncio
async def test_rejects_hasta_not_in_iso_format():
    tool = _make_tool()

    with pytest.raises(ToolError, match="hasta debe tener formato YYYY-MM-DD"):
        await tool("datos_formulario.json", "val_ind_0003", hasta="31-12-2024")


@pytest.mark.asyncio
async def test_unexpected_client_error_becomes_tool_error(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("red caída")

    monkeypatch.setattr(bce, "get_indicador_diario", boom)
    tool = _make_tool()

    with pytest.raises(ToolError, match="red caída"):
        await tool("datos_formulario.json", "val_ind_0003")

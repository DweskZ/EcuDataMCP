import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import anda_client
from tools.download_anda_microdata import register_download_anda_microdata_tool


def _make_tool():
    mcp = MCPServer("test")
    register_download_anda_microdata_tool(mcp)
    return mcp._tool_manager.get_tool("download_anda_microdata").fn


async def test_missing_csrf_token_is_a_tool_error_not_an_empty_listing(monkeypatch):
    async def fake_get_survey(idno, session=None):
        return {"id": 1153, "title": "ENEMDU 2024", "data_access_type": "public"}

    async def fake_list_files(survey_id, session=None):
        raise ValueError(
            "No se encontró el token CSRF en la página get-microdata de ANDA; "
            "la página puede estar bloqueada o haber cambiado"
        )

    monkeypatch.setattr(anda_client, "get_survey", fake_get_survey)
    monkeypatch.setattr(anda_client, "list_microdata_files", fake_list_files)

    tool = _make_tool()
    with pytest.raises(ToolError, match="token CSRF"):
        await tool(idno="ENEMDU-2024", format="json")

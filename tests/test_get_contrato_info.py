import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import sercop_client
from tools.get_contrato_info import register_get_contrato_info_tool

_OCID = "ocds-5wno2w-SIE-GADPP-2025-79-2426"
_RELEASE = {
    "ocid": _OCID,
    "tag": ["tender"],
    "buyer": {"name": "GAD PICHINCHA", "id": "EC-RUC-1760003330001"},
    "tender": {"title": "Medicinas veterinarias"},
}


@pytest.fixture
def server(monkeypatch):
    mcp = MCPServer("test")
    register_get_contrato_info_tool(mcp)
    return mcp


async def test_reads_a_release_package_without_records(server, monkeypatch):
    async def fake_record(ocid, session=None):
        return {"releases": [_RELEASE]}

    monkeypatch.setattr(sercop_client, "get_contract_record", fake_record)

    result = await server.call_tool("get_contrato_info", {"ocid": _OCID, "format": "json"})

    assert "GAD PICHINCHA" in str(result)


async def test_names_the_response_keys_when_no_record(server, monkeypatch):
    async def fake_record(ocid, session=None):
        return {"uri": "x", "version": "1.1"}

    monkeypatch.setattr(sercop_client, "get_contract_record", fake_record)

    with pytest.raises(ToolError, match="claves: uri, version"):
        await server.call_tool("get_contrato_info", {"ocid": _OCID})

import base64

import httpx
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import tools.download_resource as download_resource_module
from helpers import ckan_client
from helpers.csv_reader import MAX_DOWNLOAD_BYTES
from tools.download_resource import register_download_resource_tool


def _make_tool():
    mcp = MCPServer("test")
    register_download_resource_tool(mcp)
    return mcp._tool_manager.get_tool("download_resource").fn


def _mock_resource(
    monkeypatch, *, url="https://x/archivo.rar", fmt="RAR", name="Archivo"
):
    async def fake_get_resource(resource_id, source="nacional", session=None):
        return {"url": url, "format": fmt, "name": name}

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)


async def test_json_format_returns_base64_roundtrip(monkeypatch):
    raw = b"\x50\x4b\x03\x04binary-ish-content"

    async def fake_download_bytes(url, session=None):
        return raw, False

    _mock_resource(monkeypatch)
    monkeypatch.setattr(download_resource_module, "download_bytes", fake_download_bytes)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = result.structured_content

    assert base64.b64decode(payload["content_base64"]) == raw
    assert payload["size_bytes"] == len(raw)


async def test_text_format_does_not_leak_base64_and_points_to_json(monkeypatch):
    raw = b"some bytes"

    async def fake_download_bytes(url, session=None):
        return raw, False

    _mock_resource(monkeypatch)
    monkeypatch.setattr(download_resource_module, "download_bytes", fake_download_bytes)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="text")
    text = result.content[0].text

    # The actual encoded payload must not leak in text mode, only a
    # pointer to format="json" for retrieving it.
    assert base64.b64encode(raw).decode("ascii") not in text
    assert 'format="json"' in text


async def test_resource_not_found(monkeypatch):
    async def fake_get_resource(resource_id, source="nacional", session=None):
        request = httpx.Request("GET", "https://x/resource_show")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)

    tool = _make_tool()
    with pytest.raises(ToolError, match="no encontrado"):
        await tool(resource_id="missing", format="json")


async def test_resource_without_url(monkeypatch):
    async def fake_get_resource(resource_id, source="nacional", session=None):
        return {"format": "RAR", "name": "Sin URL"}

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)

    tool = _make_tool()
    with pytest.raises(ToolError, match="no tiene URL de descarga"):
        await tool(resource_id="abc123", format="json")


async def test_download_http_error(monkeypatch):
    async def fake_download_bytes(url, session=None):
        raise httpx.ConnectError("boom")

    _mock_resource(monkeypatch)
    monkeypatch.setattr(download_resource_module, "download_bytes", fake_download_bytes)

    tool = _make_tool()
    with pytest.raises(ToolError, match="download_failed"):
        await tool(resource_id="abc123", format="json")


async def test_oversized_file_has_no_content_base64_and_keeps_direct_url(monkeypatch):
    async def fake_download_bytes(url, session=None):
        return b"x" * 100, True

    _mock_resource(monkeypatch, url="https://x/enorme.zip", fmt="ZIP")
    monkeypatch.setattr(download_resource_module, "download_bytes", fake_download_bytes)

    tool = _make_tool()
    with pytest.raises(ToolError) as excinfo:
        await tool(resource_id="abc123", format="json")

    message = str(excinfo.value)
    assert "supera el límite" in message
    assert "https://x/enorme.zip" in message
    assert str(MAX_DOWNLOAD_BYTES // (1024 * 1024)) in message

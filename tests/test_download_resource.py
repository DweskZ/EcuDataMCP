import base64
import json

import httpx
from mcp.server.fastmcp import FastMCP

import tools.download_resource as download_resource_module
from helpers import ckan_client
from helpers.csv_reader import MAX_DOWNLOAD_BYTES
from tools.download_resource import register_download_resource_tool


def _make_tool():
    mcp = FastMCP("test")
    register_download_resource_tool(mcp)
    return mcp._tool_manager.get_tool("download_resource").fn


def _mock_resource(
    monkeypatch, *, url="https://x/archivo.rar", fmt="RAR", name="Archivo"
):
    async def fake_get_resource(resource_id, session=None):
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
    payload = json.loads(result)

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

    # The actual encoded payload must not leak in text mode, only a
    # pointer to format="json" for retrieving it.
    assert base64.b64encode(raw).decode("ascii") not in result
    assert 'format="json"' in result


async def test_resource_not_found(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        request = httpx.Request("GET", "https://x/resource_show")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)

    tool = _make_tool()
    result = await tool(resource_id="missing", format="json")
    payload = json.loads(result)
    assert payload["error"] == "not_found"


async def test_resource_without_url(monkeypatch):
    async def fake_get_resource(resource_id, session=None):
        return {"format": "RAR", "name": "Sin URL"}

    monkeypatch.setattr(ckan_client, "get_resource", fake_get_resource)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = json.loads(result)
    assert payload["error"] == "sin_url"


async def test_download_http_error(monkeypatch):
    async def fake_download_bytes(url, session=None):
        raise httpx.ConnectError("boom")

    _mock_resource(monkeypatch)
    monkeypatch.setattr(download_resource_module, "download_bytes", fake_download_bytes)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = json.loads(result)
    assert "download_failed" in payload["error"]


async def test_oversized_file_has_no_content_base64_and_keeps_direct_url(monkeypatch):
    async def fake_download_bytes(url, session=None):
        return b"x" * 100, True

    _mock_resource(monkeypatch, url="https://x/enorme.zip", fmt="ZIP")
    monkeypatch.setattr(download_resource_module, "download_bytes", fake_download_bytes)

    tool = _make_tool()
    result = await tool(resource_id="abc123", format="json")
    payload = json.loads(result)

    assert payload["error"] == "demasiado_grande"
    assert "content_base64" not in payload
    assert payload["url"] == "https://x/enorme.zip"
    assert payload["max_bytes"] == MAX_DOWNLOAD_BYTES

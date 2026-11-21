"""The smoke test skips tools a host hides on purpose instead of failing on them.

Run against the Oracle VM, which hides the tools its network cannot reach, the
script reported "Unknown tool" for each as a hard failure. /health now lists
the hidden tools and the script skips their checks; on a host that hides
nothing a missing tool is still a failure.
"""

from __future__ import annotations

import json

import httpx
import pytest

import main
from scripts import smoke_e2e as smoke


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("ECUADOR_MCP_HIDE_TOOLS", "ECUADOR_MCP_HIDE_GEOBLOCKED", "ECUADOR_MCP_GEO_PROXY"):
        monkeypatch.delenv(name, raising=False)


async def _health_json(monkeypatch=None) -> dict:
    sent: list[dict] = []

    async def inner(scope, receive, send):
        raise AssertionError("/health must be answered before the inner app")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    app = main.with_health_endpoint(inner)
    await app({"type": "http", "path": "/health", "headers": []}, receive, send)
    return json.loads(sent[1]["body"])


async def test_health_lists_the_tools_the_host_hides(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_HIDE_TOOLS", "search_contratos search_sismos")

    assert (await _health_json())["hidden_tools"] == ["search_contratos", "search_sismos"]


async def test_health_lists_no_hidden_tools_by_default():
    assert (await _health_json())["hidden_tools"] == []


async def test_a_hidden_tool_is_never_called(monkeypatch):
    monkeypatch.setattr(smoke, "HIDDEN_TOOLS", {"search_contratos"})

    with pytest.raises(smoke.HiddenTool) as exc_info:
        await smoke.call_tool(None, "search_contratos", {})  # no client: it must not be used

    assert exc_info.value.name == "search_contratos"


async def test_a_tool_that_is_not_hidden_is_still_called(monkeypatch):
    monkeypatch.setattr(smoke, "HIDDEN_TOOLS", {"search_contratos"})

    async def fake_post(client, payload):
        return {"result": {"content": [{"type": "text", "text": "hola"}], "isError": False}}

    monkeypatch.setattr(smoke, "mcp_post", fake_post)

    assert await smoke.call_tool(None, "search_sismos", {}) == ("hola", False)


def _fake_server(hidden: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "hidden_tools": hidden})
        body = json.loads(request.content or b"{}")
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": 0, "result": {}},
                headers={"mcp-session-id": "test-session"},
            )
        if method == "tools/call":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": {
                    "content": [{"type": "text", "text": "ok"}], "isError": False,
                }},
            )
        return httpx.Response(202)

    return handler


async def test_main_skips_hidden_tools_in_checks_and_chains(monkeypatch, capsys):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        smoke.httpx, "AsyncClient",
        lambda *a, **k: real_client(transport=httpx.MockTransport(_fake_server(["search_contratos"]))),
    )

    await smoke.main()
    out = capsys.readouterr().out

    assert "this host hides 1 tool(s): search_contratos" in out
    assert "SKIPPED  search_contratos: tool hidden on this host" in out
    assert "SKIPPED  sercop: search -> contrato: search_contratos is hidden on this host" in out
    assert "hidden on this host (skipped): search_contratos" in out
    assert "FAIL search_contratos" not in out


async def test_main_still_calls_every_tool_when_the_host_hides_nothing(monkeypatch, capsys):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        smoke.httpx, "AsyncClient",
        lambda *a, **k: real_client(transport=httpx.MockTransport(_fake_server([]))),
    )

    await smoke.main()
    out = capsys.readouterr().out

    assert "hidden on this host" not in out
    assert "search_contratos" in out  # called, so it is reported as an OK or a FAIL, never skipped

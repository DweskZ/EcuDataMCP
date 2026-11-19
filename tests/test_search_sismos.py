import json

import pytest
from mcp.server.mcpserver import MCPServer

from helpers import igepn_client
from helpers.cache import TtlCache
from tools.search_sismos import register_search_sismos_tool

_CSV = (
    "latitude,longitude,mag,depth,time,status,id,place\n"
    "-2.1043,-77.6736,4.30,12.9727,2026/11/15 05:53:00,confirmed,igepn2026wjlq,"
    "a 32.9 km de Tena, Napo\n"
)


@pytest.fixture
def mcp(monkeypatch):
    async def fake_get_text(url: str) -> str:
        return _CSV

    monkeypatch.setattr(igepn_client, "_get_text", fake_get_text)
    monkeypatch.setattr(igepn_client, "_events_cache", TtlCache(ttl_seconds=60))
    server = MCPServer("test")
    register_search_sismos_tool(server)
    return server


async def test_text_output_shows_event_id_and_feed_but_no_event_page_link(mcp):
    text = (await mcp.call_tool("search_sismos", {})).content[0].text

    assert "1. M 4.3 — a 32.9 km de Tena, Napo" in text
    assert "ID: igepn2026wjlq" in text
    # Per-event pages 404 for every event since IG-EPN froze them in June 2026
    assert "overview.html" not in text
    assert "Detalle:" not in text
    assert igepn_client._EVENTS_CSV_URL in text


async def test_json_events_carry_no_url(mcp):
    result = await mcp.call_tool("search_sismos", {"format": "json"})

    payload = json.loads(result.content[0].text)
    assert payload["url_fuente"] == igepn_client._EVENTS_CSV_URL
    assert payload["events"][0]["id"] == "igepn2026wjlq"
    assert "url" not in payload["events"][0]

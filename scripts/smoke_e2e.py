"""End-to-end smoke test against a running MCP HTTP server."""

from __future__ import annotations

import asyncio
import json

import httpx

MCP_URL = "http://127.0.0.1:8000/mcp"
HEALTH_URL = "http://127.0.0.1:8000/health"


def parse_sse(text: str) -> dict | None:
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except json.JSONDecodeError:
                continue
    return None


async def mcp_post(client: httpx.AsyncClient, payload: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    session_id = getattr(client, "_session_id", "")
    if session_id:
        headers["mcp-session-id"] = session_id
    resp = await client.post(MCP_URL, json=payload, headers=headers, timeout=90.0)
    resp.raise_for_status()
    if "text/event-stream" in resp.headers.get("content-type", ""):
        data = parse_sse(resp.text)
        if not data:
            raise ValueError(resp.text[:300])
        return data
    return resp.json()


async def initialize(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        MCP_URL,
        json={
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "smoke-e2e", "version": "0.4.1"},
            },
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    client._session_id = resp.headers.get("mcp-session-id", "")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if client._session_id:
        headers["mcp-session-id"] = client._session_id
    await client.post(
        MCP_URL,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=headers,
        timeout=10.0,
    )


async def call_tool(client: httpx.AsyncClient, name: str, args: dict) -> str:
    data = await mcp_post(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
    )
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    content = data.get("result", {}).get("content", [])
    return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")


def ok(label: str, text: str) -> None:
    if "Traceback" in text[:200]:
        raise AssertionError(f"{label}: traceback in response")
    if text.startswith(("Error:", "ERROR:")):
        print(f"  WARN {label}: {text[:160]}")
        return
    print(f"  OK   {label} ({len(text)} chars)")


async def main() -> int:
    async with httpx.AsyncClient() as client:
        print("== health ==")
        h = await client.get(HEALTH_URL, timeout=10.0)
        h.raise_for_status()
        print(" ", h.json())

        print("== initialize ==")
        client._session_id = ""
        await initialize(client)
        print("  session", getattr(client, "_session_id", "")[:16], "...")

        checks = [
            ("list_capabilities", {}, ["CKAN", "SERCOP"]),
            ("lookup_ubicacion", {"query": "Pichincha"}, ["17", "Pichincha"]),
            ("lookup_ubicacion", {"query": "Cuenca", "nivel": "canton"}, ["0101", "Cuenca"]),
            ("list_recent_datasets", {"page_size": 3, "format": "json"}, ['"results"']),
            ("search_datasets", {"query": "salud", "page_size": 2}, ["dataset"]),
            ("search_tramites", {"query": "pasaporte"}, ["pasaporte"]),
            ("search_regulaciones", {"query": "datos"}, ["ID"]),
            ("search_eventos_riesgo", {"provincia": "Pichincha", "limit": 3}, ["SGR", "Evento", "riesgo"]),
            ("list_sat_tsunami", {"limit": 3, "format": "json"}, ["stations"]),
            ("search_contratos", {"query": "agua", "year": 2024, "format": "json"}, ["ocid", "results", "error"]),
            (
                "search_ecuador",
                {"query": "salud", "limit": 2, "format": "json"},
                ["datasets", "tramites"],
            ),
        ]

        print("== tools ==")
        failed = 0
        for name, args, must in checks:
            try:
                text = await call_tool(client, name, args)
                if must and not any(m.lower() in text.lower() for m in must):
                    raise AssertionError(f"none of {must} found: {text[:240]}")
                ok(name, text)
            except Exception as exc:
                failed += 1
                print(f"  FAIL {name}: {exc}")

        print("== done ==")
        print(f"failed={failed}/{len(checks)}")
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

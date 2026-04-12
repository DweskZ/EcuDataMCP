"""
Quick test script to verify the Ecuador MCP server is working.
Run with: python test_server.py
Make sure the server is running on http://localhost:8000 first.
"""

import asyncio
import json
import httpx

MCP_URL = "http://localhost:8000/mcp"


def parse_sse_response(text: str) -> dict | None:
    """Parse SSE response to extract JSON-RPC result."""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except json.JSONDecodeError:
                continue
    return None


async def mcp_request(client: httpx.AsyncClient, payload: dict) -> dict:
    """Send a JSON-RPC request to the MCP server and parse the SSE response."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if hasattr(client, "_session_id") and client._session_id:
        headers["mcp-session-id"] = client._session_id

    resp = await client.post(MCP_URL, json=payload, headers=headers, timeout=30.0)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")

    if "text/event-stream" in content_type:
        data = parse_sse_response(resp.text)
        if data:
            return data
        raise ValueError(f"Could not parse SSE: {resp.text[:200]}")

    return resp.json()


async def initialize(client: httpx.AsyncClient) -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0.1.0"},
        },
    }
    resp = await client.post(
        MCP_URL,
        json=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        timeout=10.0,
    )
    resp.raise_for_status()
    session_id = resp.headers.get("mcp-session-id", "")
    client._session_id = session_id

    # Send initialized notification
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["mcp-session-id"] = session_id
    await client.post(MCP_URL, json=notif, headers=headers, timeout=10.0)


async def call_tool(client: httpx.AsyncClient, tool_name: str, args: dict) -> str:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args},
    }
    data = await mcp_request(client, payload)
    if "error" in data:
        return f"ERROR: {data['error']}"
    content = data.get("result", {}).get("content", [])
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    return "\n".join(texts)


def print_preview(result: str, max_lines: int = 10) -> None:
    lines = result.split("\n")[:max_lines]
    for line in lines:
        print(f"  {line}")
    if len(result.split("\n")) > max_lines:
        print("  ...")


async def main() -> None:
    async with httpx.AsyncClient() as client:
        client._session_id = ""
        print("=" * 60)
        print("  ECUADOR MCP SERVER - TEST COMPLETO")
        print("=" * 60)

        print("\n[1/6] Inicializando sesion MCP...")
        await initialize(client)
        print("  OK\n")

        print("[2/6] Listando categorias tematicas...")
        result = await call_tool(client, "list_categories", {})
        print_preview(result)
        print()

        print("[3/6] Buscando datasets del SRI...")
        result = await call_tool(client, "search_datasets", {"query": "SRI recaudacion", "page_size": 3})
        print_preview(result, 15)
        print()

        print("[4/6] Buscando organizacion INEC...")
        result = await call_tool(client, "search_organizations", {"query": "INEC"})
        print_preview(result)
        print()

        print("[5/6] Preview de datos CSV...")
        search = await call_tool(client, "search_datasets", {"query": "vuelos companias nacionales", "page_size": 1})
        dataset_id = None
        for line in search.split("\n"):
            if "ID:" in line and "Dataset" not in line and "Resource" not in line:
                dataset_id = line.split("ID:")[-1].strip()
                break

        if dataset_id:
            resources = await call_tool(client, "list_dataset_resources", {"dataset_id": dataset_id})
            resource_id = None
            for line in resources.split("\n"):
                if "Resource ID:" in line:
                    resource_id = line.split("Resource ID:")[-1].strip()
                    break

            if resource_id:
                preview = await call_tool(client, "preview_resource_data", {"resource_id": resource_id, "rows": 3})
                print_preview(preview, 12)
            else:
                print("  No CSV resource found")
        else:
            print("  No dataset found for preview test")
        print()

        print("[6/6] Buscando tramites...")
        result = await call_tool(client, "search_tramites", {"query": "pasaporte"})
        print_preview(result)
        print()

        print("=" * 60)
        print("  TODAS LAS PRUEBAS COMPLETADAS!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

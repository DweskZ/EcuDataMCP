"""Regression test for docs/MCP_ARCHITECTURE.md's Phase 2 (tool metadata).

Every tool registered on this server must declare a title and MCP
annotations -- this is what lets a client tell a read-only lookup apart
from the two operator tools that write local artifacts, and show a
human-readable name instead of the raw Python function name. A new tool
that forgets `title=`/`annotations=` on its `@mcp.tool()` call should fail
CI here rather than silently shipping without them.
"""

import asyncio

from mcp.server.mcpserver import MCPServer

from tools import register_maintenance_tools, register_tools

_MAINTENANCE_TOOL_NAMES = {"audit_bce_catalog", "compare_bce_sources"}


def _all_tools():
    mcp = MCPServer("test")
    register_tools(mcp)
    register_maintenance_tools(mcp)
    return asyncio.run(mcp.list_tools())


def test_every_tool_declares_a_title():
    tools = _all_tools()
    assert tools
    missing = sorted(t.name for t in tools if not t.title)
    assert not missing, f"tools missing title=: {missing}"


def test_every_tool_declares_annotations():
    tools = _all_tools()
    missing = sorted(t.name for t in tools if t.annotations is None)
    assert not missing, f"tools missing annotations=: {missing}"


def test_only_maintenance_tools_are_not_read_only():
    tools = _all_tools()
    non_read_only = sorted(
        t.name for t in tools if not (t.annotations and t.annotations.read_only_hint)
    )
    assert non_read_only == sorted(_MAINTENANCE_TOOL_NAMES)

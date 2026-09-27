"""MCPServer with a smaller tools/list.

Pydantic gives every generated JSON schema a "title": each argument model
("search_mef_fiscalArguments"), each property ("Query", "Format") and each
output model. They carry no information an agent uses -- the property name
is already the key -- yet tools/list is sent into every conversation's
context, so across ~110 tools they add up (docs/MCP_ARCHITECTURE.md,
phase 4). This subclass drops them when listing tools; argument validation
still uses the SDK's full models.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import Tool as MCPTool


def strip_schema_titles(schema: Any) -> Any:
    """Return a copy of a JSON schema without "title" annotations.

    Keys inside "properties"/"$defs" are names, not schema keywords, so a
    property that is itself called "title" survives.
    """
    if isinstance(schema, list):
        return [strip_schema_titles(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    stripped = {}
    for key, value in schema.items():
        if key == "title":
            continue
        if key in ("properties", "$defs", "definitions") and isinstance(value, dict):
            stripped[key] = {name: strip_schema_titles(sub) for name, sub in value.items()}
        else:
            stripped[key] = strip_schema_titles(value)
    return stripped


class EcuadorMCPServer(MCPServer):
    async def list_tools(self) -> list[MCPTool]:
        tools = await super().list_tools()
        for tool in tools:
            tool.input_schema = strip_schema_titles(tool.input_schema)
            if tool.output_schema is not None:
                tool.output_schema = strip_schema_titles(tool.output_schema)
        return tools

from mcp.server.mcpserver import MCPServer

from resources.catalog import register_catalog_resources


def register_resources(mcp: MCPServer) -> None:
    """Register static/dynamic MCP resources for agent context."""
    register_catalog_resources(mcp)

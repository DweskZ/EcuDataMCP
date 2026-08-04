from mcp.server.fastmcp import FastMCP

from resources.catalog import register_catalog_resources


def register_resources(mcp: FastMCP) -> None:
    """Register static/dynamic MCP resources for agent context."""
    register_catalog_resources(mcp)

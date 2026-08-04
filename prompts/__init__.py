from mcp.server.fastmcp import FastMCP

from prompts.workflows import register_workflow_prompts


def register_prompts(mcp: FastMCP) -> None:
    """Register reusable MCP prompts that guide common Ecuador workflows."""
    register_workflow_prompts(mcp)

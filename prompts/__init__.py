from mcp.server.mcpserver import MCPServer

from prompts.workflows import register_workflow_prompts


def register_prompts(mcp: MCPServer) -> None:
    """Register reusable MCP prompts that guide common Ecuador workflows."""
    register_workflow_prompts(mcp)

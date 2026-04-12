from mcp.server.fastmcp import FastMCP

from tools.get_dataset_info import register_get_dataset_info_tool
from tools.get_organization_info import register_get_organization_info_tool
from tools.get_resource_info import register_get_resource_info_tool
from tools.get_tramite_info import register_get_tramite_info_tool
from tools.list_categories import register_list_categories_tool
from tools.list_dataset_resources import register_list_dataset_resources_tool
from tools.list_instituciones import register_list_instituciones_tool
from tools.preview_resource_data import register_preview_resource_data_tool
from tools.search_datasets import register_search_datasets_tool
from tools.search_organizations import register_search_organizations_tool
from tools.search_tramites import register_search_tramites_tool


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools with the provided FastMCP instance."""
    register_search_datasets_tool(mcp)
    register_get_dataset_info_tool(mcp)
    register_list_dataset_resources_tool(mcp)
    register_get_resource_info_tool(mcp)
    register_preview_resource_data_tool(mcp)
    register_search_organizations_tool(mcp)
    register_get_organization_info_tool(mcp)
    register_list_categories_tool(mcp)
    register_search_tramites_tool(mcp)
    register_get_tramite_info_tool(mcp)
    register_list_instituciones_tool(mcp)

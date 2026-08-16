from mcp.server.fastmcp import FastMCP

from tools.download_anda_microdata import register_download_anda_microdata_tool
from tools.get_anda_survey_info import register_get_anda_survey_info_tool
from tools.get_auditor_info import register_get_auditor_info_tool
from tools.get_category_info import register_get_category_info_tool
from tools.get_compania_info import register_get_compania_info_tool
from tools.get_contrato_info import register_get_contrato_info_tool
from tools.get_dataset_info import register_get_dataset_info_tool
from tools.get_financials import register_get_financials_tool
from tools.get_institucion_info import register_get_institucion_info_tool
from tools.get_organization_info import register_get_organization_info_tool
from tools.get_regulacion_info import register_get_regulacion_info_tool
from tools.get_resource_info import register_get_resource_info_tool
from tools.get_tramite_info import register_get_tramite_info_tool
from tools.list_capabilities import register_list_capabilities_tool
from tools.list_categories import register_list_categories_tool
from tools.list_dataset_resources import register_list_dataset_resources_tool
from tools.list_instituciones import register_list_instituciones_tool
from tools.list_recent_datasets import register_list_recent_datasets_tool
from tools.list_sat_tsunami import register_list_sat_tsunami_tool
from tools.lookup_ubicacion import register_lookup_ubicacion_tool
from tools.preview_resource_data import register_preview_resource_data_tool
from tools.query_resource_data import register_query_resource_data_tool
from tools.search_anda import register_search_anda_tool
from tools.search_auditores import register_search_auditores_tool
from tools.search_companias import register_search_companias_tool
from tools.search_contratos import register_search_contratos_tool
from tools.search_datasets import register_search_datasets_tool
from tools.search_ecuador import register_search_ecuador_tool
from tools.search_eventos_riesgo import register_search_eventos_riesgo_tool
from tools.search_organizations import register_search_organizations_tool
from tools.search_ranking import register_search_ranking_tool
from tools.search_regulaciones import register_search_regulaciones_tool
from tools.search_sismos import register_search_sismos_tool
from tools.search_tramites import register_search_tramites_tool


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools with the provided FastMCP instance."""
    register_list_capabilities_tool(mcp)
    register_search_ecuador_tool(mcp)
    register_lookup_ubicacion_tool(mcp)
    register_search_eventos_riesgo_tool(mcp)
    register_list_sat_tsunami_tool(mcp)
    register_search_sismos_tool(mcp)

    register_search_datasets_tool(mcp)
    register_list_recent_datasets_tool(mcp)
    register_get_dataset_info_tool(mcp)
    register_list_dataset_resources_tool(mcp)
    register_get_resource_info_tool(mcp)
    register_preview_resource_data_tool(mcp)
    register_query_resource_data_tool(mcp)
    register_search_organizations_tool(mcp)
    register_get_organization_info_tool(mcp)
    register_list_categories_tool(mcp)
    register_get_category_info_tool(mcp)

    register_search_tramites_tool(mcp)
    register_get_tramite_info_tool(mcp)
    register_list_instituciones_tool(mcp)
    register_get_institucion_info_tool(mcp)

    register_search_anda_tool(mcp)
    register_get_anda_survey_info_tool(mcp)
    register_download_anda_microdata_tool(mcp)

    register_search_regulaciones_tool(mcp)
    register_get_regulacion_info_tool(mcp)

    register_search_contratos_tool(mcp)
    register_get_contrato_info_tool(mcp)

    register_search_companias_tool(mcp)
    register_get_compania_info_tool(mcp)
    register_search_ranking_tool(mcp)
    register_get_financials_tool(mcp)
    register_search_auditores_tool(mcp)
    register_get_auditor_info_tool(mcp)

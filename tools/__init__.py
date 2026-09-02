from mcp.server.fastmcp import FastMCP

from tools.audit_bce_catalog import register_audit_bce_catalog_tool
from tools.compare_bce_sources import register_compare_bce_sources_tool
from tools.describe_sri_saiku_cube import register_describe_sri_saiku_cube_tool
from tools.detect_series_pattern import register_detect_series_pattern_tool
from tools.download_anda_microdata import register_download_anda_microdata_tool
from tools.download_resource import register_download_resource_tool
from tools.get_anda_survey_info import register_get_anda_survey_info_tool
from tools.get_auditor_info import register_get_auditor_info_tool
from tools.get_bce_iem_table import register_get_bce_iem_table_tool
from tools.get_bce_indicador_diario import register_get_bce_indicador_diario_tool
from tools.get_category_info import register_get_category_info_tool
from tools.get_cenace_tablero import register_get_cenace_tablero_tool
from tools.get_compania_info import register_get_compania_info_tool
from tools.get_contraloria_informe import register_get_contraloria_informe_tool
from tools.get_contrato_info import register_get_contrato_info_tool
from tools.get_dataset_info import register_get_dataset_info_tool
from tools.get_financials import register_get_financials_tool
from tools.get_indicador_bce import register_get_indicador_bce_tool
from tools.get_inec_estadistica_files import register_get_inec_estadistica_files_tool
from tools.get_inec_publicacion_archivos import (
    register_get_inec_publicacion_archivos_tool,
)
from tools.get_informe_igepn import register_get_informe_igepn_tool
from tools.get_institucion_info import register_get_institucion_info_tool
from tools.get_organization_info import register_get_organization_info_tool
from tools.get_regulacion_info import register_get_regulacion_info_tool
from tools.get_resource_info import register_get_resource_info_tool
from tools.get_sipa_modulo_archivos import register_get_sipa_modulo_archivos_tool
from tools.get_sri_ruc_info import register_get_sri_ruc_info_tool
from tools.get_superbancos_seccion_archivos import (
    register_get_superbancos_seccion_archivos_tool,
)
from tools.get_sut_indicador_schema import register_get_sut_indicador_schema_tool
from tools.get_tramite_estadisticas import register_get_tramite_estadisticas_tool
from tools.get_tramite_info import register_get_tramite_info_tool
from tools.investigate_dataset import register_investigate_dataset_tool
from tools.list_bce_indicadores_diarios import (
    register_list_bce_indicadores_diarios_tool,
)
from tools.list_capabilities import register_list_capabilities_tool
from tools.list_categories import register_list_categories_tool
from tools.list_contraloria_informes import register_list_contraloria_informes_tool
from tools.list_dataset_resources import register_list_dataset_resources_tool
from tools.list_instituciones import register_list_instituciones_tool
from tools.list_recent_datasets import register_list_recent_datasets_tool
from tools.list_sat_tsunami import register_list_sat_tsunami_tool
from tools.list_sipa_modulos import register_list_sipa_modulos_tool
from tools.list_sri_saiku_cubes import register_list_sri_saiku_cubes_tool
from tools.list_superbancos_secciones import register_list_superbancos_secciones_tool
from tools.list_sut_indicadores import register_list_sut_indicadores_tool
from tools.list_zip_contents import register_list_zip_contents_tool
from tools.lookup_ubicacion import register_lookup_ubicacion_tool
from tools.preview_resource_data import register_preview_resource_data_tool
from tools.query_resource_data import register_query_resource_data_tool
from tools.query_sri_saiku_aggregate import register_query_sri_saiku_aggregate_tool
from tools.query_sut_indicador import register_query_sut_indicador_tool
from tools.read_pdf import register_read_pdf_tool
from tools.search_anda import register_search_anda_tool
from tools.search_auditores import register_search_auditores_tool
from tools.search_bce_iem import register_search_bce_iem_tool
from tools.search_bce_publicaciones import register_search_bce_publicaciones_tool
from tools.search_bce_remesas import register_search_bce_remesas_tool
from tools.search_biinec_extras import register_search_biinec_extras_tool
from tools.search_censo_recursos import register_search_censo_recursos_tool
from tools.search_companias import register_search_companias_tool
from tools.search_contratos import register_search_contratos_tool
from tools.search_datasets import register_search_datasets_tool
from tools.search_ecuador import register_search_ecuador_tool
from tools.search_eventos_riesgo import register_search_eventos_riesgo_tool
from tools.search_indicadores_bce import register_search_indicadores_bce_tool
from tools.search_inec_estadisticas import register_search_inec_estadisticas_tool
from tools.search_inec_publicaciones import register_search_inec_publicaciones_tool
from tools.search_informes_igepn import register_search_informes_igepn_tool
from tools.search_organizations import register_search_organizations_tool
from tools.search_ranking import register_search_ranking_tool
from tools.search_regulaciones import register_search_regulaciones_tool
from tools.search_sismos import register_search_sismos_tool
from tools.search_sri_datasets import register_search_sri_datasets_tool
from tools.search_sri_estadisticas_recaudacion import (
    register_search_sri_estadisticas_recaudacion_tool,
)
from tools.search_sri_ruc import register_search_sri_ruc_tool
from tools.search_tramites import register_search_tramites_tool


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools with the provided FastMCP instance."""
    register_list_capabilities_tool(mcp)
    register_search_ecuador_tool(mcp)
    register_lookup_ubicacion_tool(mcp)
    register_search_eventos_riesgo_tool(mcp)
    register_list_sat_tsunami_tool(mcp)
    register_search_sismos_tool(mcp)
    register_search_informes_igepn_tool(mcp)
    register_get_informe_igepn_tool(mcp)

    register_search_datasets_tool(mcp)
    register_list_recent_datasets_tool(mcp)
    register_get_dataset_info_tool(mcp)
    register_list_dataset_resources_tool(mcp)
    register_get_resource_info_tool(mcp)
    register_preview_resource_data_tool(mcp)
    register_detect_series_pattern_tool(mcp)
    register_download_resource_tool(mcp)
    register_query_resource_data_tool(mcp)
    register_search_organizations_tool(mcp)
    register_get_organization_info_tool(mcp)
    register_list_categories_tool(mcp)
    register_get_category_info_tool(mcp)
    register_search_sri_datasets_tool(mcp)
    register_search_sri_estadisticas_recaudacion_tool(mcp)
    register_get_sri_ruc_info_tool(mcp)
    register_search_sri_ruc_tool(mcp)
    register_list_sri_saiku_cubes_tool(mcp)
    register_describe_sri_saiku_cube_tool(mcp)
    register_query_sri_saiku_aggregate_tool(mcp)
    register_read_pdf_tool(mcp)
    register_list_zip_contents_tool(mcp)
    register_investigate_dataset_tool(mcp)

    register_search_tramites_tool(mcp)
    register_get_tramite_info_tool(mcp)
    register_get_tramite_estadisticas_tool(mcp)
    register_list_instituciones_tool(mcp)
    register_get_institucion_info_tool(mcp)

    register_search_anda_tool(mcp)
    register_get_anda_survey_info_tool(mcp)
    register_download_anda_microdata_tool(mcp)

    register_search_inec_estadisticas_tool(mcp)
    register_get_inec_estadistica_files_tool(mcp)
    register_search_inec_publicaciones_tool(mcp)
    register_get_inec_publicacion_archivos_tool(mcp)
    register_search_biinec_extras_tool(mcp)
    register_search_censo_recursos_tool(mcp)

    register_search_regulaciones_tool(mcp)
    register_get_regulacion_info_tool(mcp)

    register_list_sipa_modulos_tool(mcp)
    register_get_sipa_modulo_archivos_tool(mcp)

    register_list_superbancos_secciones_tool(mcp)
    register_get_superbancos_seccion_archivos_tool(mcp)

    register_list_sut_indicadores_tool(mcp)
    register_get_sut_indicador_schema_tool(mcp)
    register_query_sut_indicador_tool(mcp)

    register_list_contraloria_informes_tool(mcp)
    register_get_contraloria_informe_tool(mcp)

    register_search_contratos_tool(mcp)
    register_get_contrato_info_tool(mcp)

    register_search_indicadores_bce_tool(mcp)
    register_get_indicador_bce_tool(mcp)
    register_audit_bce_catalog_tool(mcp)
    register_compare_bce_sources_tool(mcp)
    register_search_bce_iem_tool(mcp)
    register_get_bce_iem_table_tool(mcp)
    register_search_bce_publicaciones_tool(mcp)
    register_search_bce_remesas_tool(mcp)
    register_list_bce_indicadores_diarios_tool(mcp)
    register_get_bce_indicador_diario_tool(mcp)
    register_get_cenace_tablero_tool(mcp)

    register_search_companias_tool(mcp)
    register_get_compania_info_tool(mcp)
    register_search_ranking_tool(mcp)
    register_get_financials_tool(mcp)
    register_search_auditores_tool(mcp)
    register_get_auditor_info_tool(mcp)

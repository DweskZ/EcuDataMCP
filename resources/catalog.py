import json

from mcp.server.fastmcp import FastMCP

from helpers.geo_data import list_cantones, list_parroquias, list_provincias

_INSTITUCIONES_CLAVE = [
    {"id": "8", "nombre": "SRI", "uso": "impuestos, RUC, facturación"},
    {"id": "5", "nombre": "IESS", "uso": "seguro social, pensiones"},
    {"id": "23", "nombre": "Registro Civil", "uso": "cédula, partidas"},
    {"id": "62", "nombre": "ANT", "uso": "licencias, matriculación"},
    {"id": "16", "nombre": "Cancillería", "uso": "pasaporte, apostilla, visas"},
]

_CKAN_TOOLS = [
    "search_datasets",
    "list_recent_datasets",
    "get_dataset_info",
    "list_dataset_resources",
    "get_resource_info",
    "preview_resource_data",
    "download_resource",
    "query_resource_data",
    "detect_series_pattern",
    "read_pdf",
    "search_organizations",
    "get_organization_info",
    "list_categories",
    "get_category_info",
]


def _fuentes_payload() -> dict:
    return {
        "fuentes": [
            {
                "id": "ckan",
                "nombre": "Datos Abiertos CKAN",
                "base": "https://www.datosabiertos.gob.ec/",
                "tools": _CKAN_TOOLS,
            },
            {
                "id": "cuenca",
                "nombre": "Cuenca en Datos (portal municipal CKAN, independiente del nacional)",
                "base": "https://cuencaendatos.cuenca.gob.ec/",
                "tools": _CKAN_TOOLS,
            },
            {
                "id": "sri",
                "nombre": "SRI Datasets (fuera del portal CKAN)",
                "base": "https://www.sri.gob.ec/datasets",
                "tools": ["search_sri_datasets"],
            },
            {
                "id": "gobec",
                "nombre": "gob.ec trámites / instituciones / regulaciones",
                "base": "https://www.gob.ec/api/v1/",
                "tools": [
                    "search_tramites",
                    "get_tramite_info",
                    "search_regulaciones",
                    "get_regulacion_info",
                    "list_instituciones",
                    "get_institucion_info",
                ],
            },
            {
                "id": "sercop",
                "nombre": "SERCOP Contrataciones Abiertas OCDS",
                "base": "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/",
                "tools": ["search_contratos", "get_contrato_info"],
            },
            {
                "id": "sgr",
                "nombre": "SGR Gestión de Riesgos (COE + SAT)",
                "base": "https://sgrportal.gestionderiesgos.gob.ec/server/rest/services",
                "tools": ["search_eventos_riesgo", "list_sat_tsunami"],
            },
            {
                "id": "igepn",
                "nombre": "Instituto Geofísico EPN (catálogo sísmico)",
                "base": "https://www.igepn.edu.ec/portal/eventos/www/",
                "tools": ["search_sismos"],
            },
            {
                "id": "geo",
                "nombre": "DPA provincias, cantones y parroquias (referencia offline INEC)",
                "tools": ["lookup_ubicacion"],
            },
            {
                "id": "anda",
                "nombre": "ANDA / INEC (encuestas, censos y microdatos)",
                "base": "https://anda.inec.gob.ec/anda5/",
                "tools": [
                    "search_anda",
                    "get_anda_survey_info",
                    "download_anda_microdata",
                ],
            },
            {
                "id": "inec-estadisticas",
                "nombre": "Ecuador en Cifras / INEC (estadísticas publicadas)",
                "base": "https://www.ecuadorencifras.gob.ec/",
                "tools": [
                    "search_inec_estadisticas",
                    "get_inec_estadistica_files",
                    "search_inec_publicaciones",
                    "get_inec_publicacion_archivos",
                ],
            },
            {
                "id": "inec-biinec",
                "nombre": "BIINEC / INEC (registros exclusivos curados)",
                "base": "https://aplicaciones3.ecuadorencifras.gob.ec/BIINEC-war/",
                "tools": ["search_biinec_extras"],
            },
            {
                "id": "bce",
                "nombre": "Banco Central del Ecuador (BCEData + Información Estadística Mensual)",
                "base": "https://contenido.bce.fin.ec/",
                "tools": [
                    "search_indicadores_bce",
                    "get_indicador_bce",
                    "search_bce_iem",
                    "get_bce_iem_table",
                    "audit_bce_catalog",
                ],
            },
            {
                "id": "sipa",
                "nombre": "SIPA / Ministerio de Agricultura (estadísticas agropecuarias)",
                "base": "https://sipa.agricultura.gob.ec/",
                "tools": ["list_sipa_modulos", "get_sipa_modulo_archivos"],
            },
            {
                "id": "contraloria",
                "nombre": "Contraloría General del Estado (informes de auditoría)",
                "base": "https://www.contraloria.gob.ec/Portal/24287",
                "tools": [
                    "list_contraloria_informes",
                    "get_contraloria_informe",
                ],
            },
            {
                "id": "supercias",
                "nombre": (
                    "Superintendencia de Compañías (directorio de compañías, "
                    "auditores externos)"
                ),
                "base": "https://mercadodevalores.supercias.gob.ec/reportes/",
                "tools": [
                    "search_companias",
                    "get_compania_info",
                    "search_auditores",
                    "get_auditor_info",
                ],
            },
            {
                "id": "supercias-financials",
                "nombre": "Superintendencia de Compañías (ranking financiero, últimos años)",
                "base": "https://appscvsmovil.supercias.gob.ec/ranking/",
                "tools": ["search_ranking", "get_financials"],
            },
        ]
    }


def register_catalog_resources(mcp: FastMCP) -> None:
    @mcp.resource(
        "ecuador://fuentes",
        name="fuentes_ecuador",
        title="Fuentes del MCP Ecuador",
        description="Catálogo de fuentes gubernamentales integradas en este servidor.",
        mime_type="application/json",
    )
    def fuentes() -> str:
        return json.dumps(_fuentes_payload(), ensure_ascii=False, indent=2)

    @mcp.resource(
        "ecuador://provincias",
        name="provincias_ecuador",
        title="Provincias del Ecuador",
        description="24 provincias con código INEC, capital y región natural.",
        mime_type="application/json",
    )
    def provincias() -> str:
        return json.dumps(list_provincias(), ensure_ascii=False, indent=2)

    @mcp.resource(
        "ecuador://cantones",
        name="cantones_ecuador",
        title="Cantones del Ecuador",
        description="Cantones con código INEC, provincia, región y población estimada.",
        mime_type="application/json",
    )
    def cantones() -> str:
        return json.dumps(list_cantones(), ensure_ascii=False, indent=2)

    @mcp.resource(
        "ecuador://parroquias",
        name="parroquias_ecuador",
        title="Parroquias del Ecuador",
        description="Parroquias con código INEC, cantón y provincia (~1040).",
        mime_type="application/json",
    )
    def parroquias() -> str:
        return json.dumps(list_parroquias(), ensure_ascii=False, indent=2)

    @mcp.resource(
        "ecuador://instituciones-clave",
        name="instituciones_clave",
        title="Instituciones clave gob.ec",
        description="IDs frecuentes para search_tramites(institution_id=...).",
        mime_type="application/json",
    )
    def instituciones_clave() -> str:
        return json.dumps(_INSTITUCIONES_CLAVE, ensure_ascii=False, indent=2)

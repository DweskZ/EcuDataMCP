import json

from mcp.server.mcpserver import MCPServer

from helpers.geo_data import list_cantones, list_parroquias, list_provincias
from helpers.geo_proxy import hidden_tools
from helpers.logging import TOOL_DOCS

_INSTITUCIONES_CLAVE = [
    {"id": "8", "nombre": "SRI", "uso": "impuestos, RUC, facturación"},
    {"id": "163", "nombre": "IESS", "uso": "seguro social, pensiones"},
    {"id": "23", "nombre": "Registro Civil", "uso": "cédula, partidas"},
    {"id": "48", "nombre": "ANT", "uso": "licencias, matriculación"},
    {"id": "6", "nombre": "Cancillería", "uso": "pasaporte, apostilla, visas"},
]

_CKAN_TOOLS = [
    "search_datasets",
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
    payload = _all_fuentes()
    hidden = hidden_tools()
    if not hidden:
        return payload

    # Drop tools this deployment doesn't register, and sources left empty.
    fuentes = []
    for fuente in payload["fuentes"]:
        tools = [tool for tool in fuente["tools"] if tool not in hidden]
        if tools:
            fuentes.append({**fuente, "tools": tools})
    return {**payload, "fuentes": fuentes}


def _all_fuentes() -> dict:
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
                "id": "latacunga",
                "nombre": "Data Mashca (portal municipal CKAN de Latacunga, independiente del nacional)",
                "base": "https://datosabiertos.latacunga.gob.ec/",
                "tools": _CKAN_TOOLS,
            },
            {
                "id": "sri",
                "nombre": (
                    "SRI: datasets fuera de CKAN, RUC y estadísticas de recaudación"
                ),
                "base": "https://www.sri.gob.ec/datasets",
                "tools": [
                    "search_archivos",
                    "get_sri_ruc_info",
                    "search_sri_ruc",
                ],
            },
            {
                "id": "arcsa",
                "nombre": "ARCSA Base de Registros Emitidos (registro sanitario vigente)",
                "base": "https://www.controlsanitario.gob.ec/base-de-datos/",
                "tools": ["list_archivo_secciones", "get_archivo_seccion"],
            },
            {
                "id": "gobec",
                "nombre": "gob.ec trámites / instituciones / regulaciones",
                "base": "https://www.gob.ec/api/v1/",
                "tools": [
                    "search_tramites",
                    "get_tramite_info",
                    "get_tramite_estadisticas",
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
                "id": "sgr-publicaciones",
                "nombre": "SGR Gestión de Riesgos (SITREP de eventos adversos y Biblioteca)",
                "base": "https://www.gestionderiesgos.gob.ec/",
                "tools": [
                    "search_sgr_sitreps",
                    "get_sgr_sitrep_archivos",
                    "list_archivo_secciones",
                    "get_archivo_seccion",
                ],
            },
            {
                "id": "inamhi",
                "nombre": "INAMHI (geoportal hidrometeorológico, capas WMS/WFS)",
                "base": "https://geoservicios.inamhi.gob.ec/geoserver",
                "tools": ["search_capas_geo", "get_capa_geo_datos"],
            },
            {
                "id": "aviacion",
                "nombre": "DGAC / AIS Ecuador (AIP de aeródromos, METAR, NOTAM, SIGMET)",
                "base": "https://www.ais.aviacioncivil.gob.ec/",
                "tools": [
                    "list_aip_aerodromos",
                    "get_aip_aerodromo",
                    "get_aviso_aeronautico",
                ],
            },
            {
                "id": "igepn",
                "nombre": "Instituto Geofísico EPN (catálogo sísmico + informes sísmicos/volcánicos)",
                "base": "https://www.igepn.edu.ec/portal/eventos/www/",
                "tools": [
                    "search_sismos",
                    "search_informes_igepn",
                    "get_informe_igepn",
                ],
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
                "id": "inec-censo",
                "nombre": "Censo Ecuador 2022 / INEC (microdatos completos del censo)",
                "base": "https://www.censoecuador.gob.ec/",
                "tools": ["search_archivos"],
            },
            {
                "id": "bce",
                "nombre": (
                    "Banco Central del Ecuador (BCEData, Información "
                    "Estadística Mensual, indicadores diarios en línea y "
                    "remesas de trabajadores)"
                ),
                "base": "https://contenido.bce.fin.ec/",
                "tools": [
                    "search_indicadores_bce",
                    "get_indicador_bce",
                    "audit_bce_catalog",
                    "compare_bce_sources",
                    "search_bce_iem",
                    "get_bce_iem_table",
                    "search_bce_paginas",
                    "get_bce_pagina_archivos",
                    "list_catalogo",
                    "get_bce_indicador_diario",
                    "search_bce_calendario",
                ],
            },
            {
                "id": "sipa",
                "nombre": "SIPA / Ministerio de Agricultura (estadísticas agropecuarias)",
                "base": "https://sipa.agricultura.gob.ec/",
                "tools": [
                    "list_archivo_secciones",
                    "get_archivo_seccion",
                    "get_sipa_resumen_indicadores",
                    "search_capas_geo",
                    "get_capa_geo_datos",
                ],
            },
            {
                "id": "energia",
                "nombre": (
                    "Ministerio de Ambiente y Energía (estadística de "
                    "hidrocarburos, minería y Balance Energético Nacional)"
                ),
                "base": "https://www.ambienteyenergia.gob.ec/",
                "tools": [
                    "list_archivo_secciones",
                    "get_archivo_seccion",
                    "read_pdf",
                ],
            },
            {
                "id": "contraloria",
                "nombre": "Contraloría General del Estado (informes de auditoría)",
                "base": "https://www.contraloria.gob.ec/Portal/24287",
                "tools": [
                    "list_catalogo",
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
            {
                "id": "superbancos",
                "nombre": (
                    "Superintendencia de Bancos (boletines financieros, "
                    "servicios financieros, información histórica)"
                ),
                "base": "https://www.superbancos.gob.ec/estadisticas/portalestudios",
                "tools": [
                    "list_archivo_secciones",
                    "get_archivo_seccion",
                ],
            },
            {
                "id": "cenace",
                "nombre": "CENACE (snapshot en vivo de generación y demanda eléctrica)",
                "base": "https://www.cenace.gob.ec/",
                "tools": ["get_cenace_tablero"],
            },
            {
                "id": "arconel",
                "nombre": "ARCONEL (reportes estadísticos del sector eléctrico)",
                "base": "https://reportes.arconel.gob.ec/",
                "tools": ["list_catalogo", "get_arconel_reporte"],
            },
            {
                "id": "eeq",
                "nombre": "Empresa Eléctrica Quito (cronogramas de cortes de luz en PDF)",
                "base": "https://www.eeq.com.ec/",
                "tools": ["search_cortes", "get_cortes_horarios"],
            },
            {
                "id": "centrosur",
                "nombre": (
                    "Centrosur (cronogramas de cortes de luz en Azuay, Cañar "
                    "y Morona Santiago)"
                ),
                "base": "https://www.centrosur.gob.ec/",
                "tools": ["search_cortes", "get_cortes_horarios"],
            },
            {
                "id": "energia-ecuador",
                "nombre": (
                    "energia-ecuador.com vía Wayback Machine (horarios históricos "
                    "de apagones)"
                ),
                "base": "https://web.archive.org/",
                "tools": ["get_energia_ecuador_snapshot"],
            },
            {
                "id": "sut",
                "nombre": (
                    "Ministerio del Trabajo / SUT (tableros Power BI en vivo: "
                    "contratos, brechas de empleo, políticas de género)"
                ),
                "base": "https://sut.trabajo.gob.ec/",
                "tools": [
                    "list_catalogo",
                    "get_sut_indicador_schema",
                    "query_sut_indicador",
                ],
            },
            {
                "id": "arcotel",
                "nombre": (
                    "ARCOTEL (estadísticas del sector de telecomunicaciones: "
                    "reportes mensuales y boletines anuales/temáticos)"
                ),
                "base": "https://www.arcotel.gob.ec/",
                "tools": ["search_archivos"],
            },
            {
                "id": "trabajo",
                "nombre": (
                    "Ministerio del Trabajo (salarios sectoriales y boletín "
                    "estadístico anual)"
                ),
                "base": "https://www.trabajo.gob.ec/",
                "tools": [
                    "search_archivos",
                ],
            },
            {
                "id": "iess",
                "nombre": (
                    "IESS (boletines y documentos estadísticos, certificado de "
                    "cumplimiento patronal)"
                ),
                "base": "https://www.iess.gob.ec/",
                "tools": [
                    "list_catalogo",
                    "get_iess_archivos",
                    "get_certificado_cumplimiento_patronal",
                ],
            },
            {
                "id": "seps",
                "nombre": "SEPS (estadísticas de la economía popular y solidaria)",
                "base": "https://estadisticas.seps.gob.ec/",
                "tools": ["list_archivo_secciones", "get_archivo_seccion"],
            },
            {
                "id": "mef",
                "nombre": "MEF / SENAE (operaciones fiscales y tributos recaudados)",
                "base": "https://www.economicoproductivo.gob.ec/",
                "tools": ["search_archivos"],
            },
            {
                "id": "senescyt",
                "nombre": "SENESCYT / Educación Superior (estadísticas SIAU y Biblioteca)",
                "base": "https://siau.senescyt.gob.ec/",
                "tools": [
                    "search_archivos",
                    "list_archivo_secciones",
                    "get_archivo_seccion",
                ],
            },
            {
                "id": "minedec",
                "nombre": "MINEDEC (matrícula escolar histórica, datos abiertos)",
                "base": "https://educacion.gob.ec/datos-abiertos-minedec/",
                "tools": ["search_archivos"],
            },
            {
                "id": "ineval",
                "nombre": "INEVAL (resultados de evaluaciones educativas)",
                "base": "https://evaluaciones.evaluacion.gob.ec/BI",
                "tools": ["list_archivo_secciones", "get_archivo_seccion"],
            },
            {
                "id": "infomies",
                "nombre": "infoMIES (bases mensuales y boletines zonales del MIES)",
                "base": "https://info.desarrollohumano.gob.ec/",
                "tools": [
                    "search_infomies_bases_mensuales",
                    "search_infomies_boletines_zonales",
                ],
            },
            {
                "id": "msp",
                "nombre": "MSP (gacetas semanales de enfermedades inmunoprevenibles)",
                "base": "https://www.salud.gob.ec/",
                "tools": ["search_archivos"],
            },
            {
                "id": "cnig",
                "nombre": "CNIG (estadísticas de violencia de género y femicidios)",
                "base": "https://www.igualdadgenero.gob.ec/violencia/",
                "tools": ["search_archivos"],
            },
            {
                "id": "cepalstat",
                "nombre": "CEPALSTAT (indicadores de CEPAL filtrados a Ecuador)",
                "base": "https://api-cepalstat.cepal.org/cepalstat/api/v1",
                "tools": ["search_cepalstat_indicadores", "get_cepalstat_indicador"],
            },
            {
                "id": "series_internacionales",
                "nombre": "Series internacionales con Ecuador: Banco Mundial WDI, IRENA, XM Colombia",
                "base": "https://api.worldbank.org/v2",
                "tools": ["get_serie_internacional"],
            },
            {
                "id": "utilidades",
                "nombre": "Utilidades transversales (búsqueda global, archivos, orientación)",
                "tools": [
                    "search_ecuador",
                    "investigate_dataset",
                    "list_zip_contents",
                ],
            },
        ]
    }


def register_catalog_resources(mcp: MCPServer) -> None:
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
        "ecuador://herramientas/{nombre}",
        name="referencia_herramienta",
        title="Referencia completa de una herramienta",
        description=(
            "Documentación completa de una tool (alcance, parámetros, límites de "
            "la fuente); tools/list solo lleva un resumen."
        ),
        mime_type="text/plain",
    )
    def herramienta(nombre: str) -> str:
        if nombre not in TOOL_DOCS:
            raise ValueError(
                f"Tool '{nombre}' no existe. Ver tools/list o ecuador://fuentes."
            )
        return TOOL_DOCS[nombre]

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

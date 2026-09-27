from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY
from helpers.version import get_version

_CAPABILITIES = {
    "name": "Ecuador MCP",
    "version": get_version(),
    "fuentes": [
        "CKAN datos abiertos (nacional, www.datosabiertos.gob.ec)",
        (
            "Cuenca en Datos y Data Mashca/Latacunga (portales municipales "
            "CKAN independientes, source='cuenca'/'latacunga' en los "
            "mismos tools CKAN)"
        ),
        "gob.ec trámites/instituciones/regulaciones + estadísticas de transparencia por trámite",
        "SERCOP OCDS contratos",
        "SGR COE eventos de riesgo + SAT tsunami",
        "IG-EPN Instituto Geofísico: catálogo sísmico + archivo de informes sísmicos/volcánicos en PDF",
        "DPA provincias/cantones/parroquias (offline INEC)",
        "ANDA (NADA/IHSN) catálogo de encuestas y censos del INEC",
        (
            "Ecuador en Cifras (INEC): boletines/metodología/series históricas "
            "por tema, API REST de publicaciones, microsito del Censo 2022 y "
            "BIINEC (registros complementarios)"
        ),
        (
            "BCE: BCEData (catálogo monetario/fiscal/externo/real), boletín "
            "mensual IEM, familia de indicadores diarios en línea (riesgo "
            "país, petróleo, oro, bonos soberanos) y remesas de trabajadores"
        ),
        "Supercías directorio de compañías",
        "Supercías registro de auditores externos autorizados",
        "Supercías ranking financiero (últimos años, requiere build local)",
        "SRI consulta pública del Registro Único de Contribuyentes (RUC)",
        "SRI estadísticas de recaudación: reportes mensuales pre-agregados por impuesto/provincia/actividad",
        "ARCSA Base de Registros Emitidos: registro sanitario vigente por categoría (alimentos, medicamentos, cosméticos, dispositivos médicos, etc.)",
        (
            "SIPA (Ministerio de Agricultura, Ganadería y Pesca): series "
            "agropecuarias reales — precios, comercio exterior, crédito, "
            "producción, censos — organizadas en 4 módulos"
        ),
        (
            "Contraloría General del Estado: CSV trimestrales de informes de "
            "auditoría aprobados a cualquier institución pública del país"
        ),
        (
            "Superintendencia de Bancos: boletines financieros mensuales, "
            "servicios financieros e información histórica"
        ),
        "CENACE: snapshot en vivo de generación y demanda de la red eléctrica nacional",
        (
            "Sector eléctrico: reportes estadísticos de ARCONEL, cronogramas de "
            "cortes de EEQ y Centrosur (PDF parseados a filas) y horarios "
            "históricos de energia-ecuador.com vía Wayback Machine"
        ),
        "DGAC/AIS: AIP de aeródromos, METAR, NOTAM y SIGMET",
        "INAMHI y geoportal del MAG: capas geográficas WMS/WFS",
        "SGR: informes de situación (SITREP) y Biblioteca de documentos",
        (
            "IESS (boletines, certificado de cumplimiento patronal), SEPS, "
            "MEF/SENAE fiscal, SENESCYT, MINEDEC, INEVAL, infoMIES, MSP y CNIG"
        ),
        "CEPALSTAT: indicadores regionales de CEPAL filtrados a Ecuador",
        (
            "Ministerio del Trabajo (SUT): tableros Power BI en vivo — "
            "contratos mensuales por industria/provincia/género desde 2015, "
            "brechas de empleo, cumplimiento de políticas de género"
        ),
        (
            "ARCOTEL: estadísticas del sector de telecomunicaciones — "
            "reportes mensuales (2017-2026) y boletines anuales/temáticos "
            "(2015-2024), ambos en PDF"
        ),
    ],
    "entrada": [
        "list_capabilities",
        "search_ecuador",
        "prompts: explorar_datos / consultar_tramite / investigar_contrato / buscar_regulacion / buscar_inec / monitorear_riesgos",
    ],
    "tools_clave": {
        "datos": [
            "search_datasets",
            "query_resource_data",
            "preview_resource_data",
            "detect_series_pattern",
            "list_categories",
            "read_pdf",
            "get_dataset_info",
            "list_dataset_resources",
            "get_resource_info",
            "download_resource",
            "get_category_info",
            "search_organizations",
            "get_organization_info",
        ],
        "tramites": [
            "search_tramites",
            "get_tramite_info",
            "get_tramite_estadisticas",
            "list_instituciones",
            "get_institucion_info",
        ],
        "normas": ["search_regulaciones", "get_regulacion_info"],
        "compras": ["search_contratos", "get_contrato_info"],
        "riesgos": [
            "search_eventos_riesgo",
            "list_sat_tsunami",
            "search_sismos",
            "search_informes_igepn",
            "get_informe_igepn",
            "search_sgr_sitreps",
            "get_sgr_sitrep_archivos",
            "list_archivo_secciones",
            "get_archivo_seccion",
            "search_inamhi_capas",
            "get_inamhi_capa_datos",
        ],
        "geo": ["lookup_ubicacion"],
        "encuestas": ["search_anda", "get_anda_survey_info", "download_anda_microdata"],
        "inec_estadisticas": [
            "search_inec_estadisticas",
            "get_inec_estadistica_files",
            "search_inec_publicaciones",
            "get_inec_publicacion_archivos",
            "search_biinec_extras",
            "search_censo_recursos",
        ],
        "macro": [
            "search_indicadores_bce",
            "get_indicador_bce",
            "audit_bce_catalog",
            "compare_bce_sources",
            "search_bce_iem",
            "get_bce_iem_table",
            "search_bce_publicaciones",
            "search_bce_indices",
            "get_bce_indice_archivo",
            "list_bce_indicadores_diarios",
            "get_bce_indicador_diario",
            "search_bce_remesas",
            "search_bce_cuentas_nacionales",
            "get_bce_cuentas_nacionales_archivo",
            "search_bce_precios_comex",
            "search_bce_calendario",
            "search_mef_fiscal",
            "search_cepalstat_indicadores",
            "get_cepalstat_indicador",
        ],
        "companias": [
            "search_companias",
            "get_compania_info",
            "search_auditores",
            "get_auditor_info",
        ],
        "sri": [
            "search_sri_datasets",
            "search_sri_estadisticas_recaudacion",
            "get_sri_ruc_info",
            "search_sri_ruc",
        ],
        "arcsa": ["list_archivo_secciones", "get_archivo_seccion"],
        "financieros": ["search_ranking", "get_financials"],
        "agropecuario": [
            "list_archivo_secciones",
            "get_archivo_seccion",
            "get_sipa_resumen_indicadores",
            "search_sipa_geoportal_capas",
            "get_sipa_geoportal_capa_datos",
        ],
        "auditoria": ["list_contraloria_informes", "get_contraloria_informe"],
        "superbancos": [
            "list_archivo_secciones",
            "get_archivo_seccion",
        ],
        "energia": [
            "get_cenace_tablero",
            "list_arconel_reportes",
            "get_arconel_reporte",
            "search_eeq_cortes",
            "get_eeq_cortes_horarios",
            "search_centrosur_cortes",
            "get_centrosur_cortes_horarios",
            "get_energia_ecuador_snapshot",
        ],
        "trabajo": [
            "list_sut_indicadores",
            "get_sut_indicador_schema",
            "query_sut_indicador",
            "search_salarios_sectoriales",
            "search_trabajo_boletin_anual",
            "list_iess_colecciones",
            "get_iess_archivos",
            "get_certificado_cumplimiento_patronal",
        ],
        "social": [
            "search_senescyt_estadisticas",
            "list_archivo_secciones",
            "get_archivo_seccion",
            "search_minedec_matricula",
            "search_infomies_bases_mensuales",
            "search_infomies_boletines_zonales",
            "search_gacetas_inmunoprevenibles",
            "search_cnig_femicidios",
        ],
        "aviacion": [
            "list_aip_aerodromos",
            "get_aip_aerodromo",
            "get_metar",
            "get_notam",
            "get_sigmet",
        ],
        "utilidades": ["investigate_dataset", "list_zip_contents"],
        "telecomunicaciones": ["search_arcotel"],
    },
    "resources": [
        "ecuador://fuentes",
        "ecuador://provincias",
        "ecuador://cantones",
        "ecuador://parroquias",
        "ecuador://instituciones-clave",
    ],
    "format": "Casi todos los tools aceptan format='json' además de text",
    "limites": [
        "CKAN puede requerir TLS insecure allowlist (CKAN_INSECURE_TLS)",
        "SERCOP a veces rate-limita (429); hay reintentos + caché negativa/TTL",
        "SGR COE es un snapshot público; no sustituye alertas oficiales en tiempo real",
        (
            "Sismos IG-EPN: feed público events.csv con hora local (UTC-5); "
            "no sustituye canales oficiales de alerta"
        ),
        "lookup_ubicacion(nivel='parroquia') requiere query, canton o provincia",
        (
            "search_indicadores_bce: primer uso tras expirar el caché (24h) "
            "puede tardar ~10-15s (arma el índice de búsqueda sobre ~78 "
            "grupos); no cubre inflación (CPI) ni pobreza de Ecuador — eso es "
            "INEC: search_anda para metadata/microdatos, "
            "search_inec_estadisticas para el boletín y la serie histórica "
            "real de índices como el IPC (ANDA los cataloga sin microdatos)"
        ),
        (
            "audit_bce_catalog consulta el árbol y los metadatos de todos los "
            "grupos BCEData; no descarga todos los valores históricos. Con "
            "auditar_grid=true prueba un período reciente por cada combinación "
            "frecuencia/unidad, hasta 500 combinaciones, y puede guardar el "
            "reporte separado. Usa get_indicador_bce para series completas. "
            "Con guardar_snapshot/comparar_anterior conserva el catálogo y "
            "detecta cambios."
        ),
        (
            "search_biinec_extras no busca en vivo dentro de BIINEC "
            "(aplicaciones3.ecuadorencifras.gob.ec) — es una lista pequeña y "
            "verificada a mano de los pocos registros confirmados exclusivos "
            "ahí; sin resultado no implica que BIINEC no tenga el dato"
        ),
        (
            "search_companias/get_compania_info: primer uso tras expirar el "
            "caché (6h) puede tardar ~30-40s (descarga y parsea ~35 MB, 226k filas)"
        ),
        (
            "get_sri_ruc_info consulta únicamente la ficha registral pública "
            "del SRI y sus establecimientos; no expone declaraciones ni "
            "montos tributarios individuales"
        ),
        (
            "search_ranking/get_financials: la base local se construye/"
            "refresca sola en segundo plano (al iniciar el servidor y ante "
            "cualquier consulta si falta o está vieja); la primera vez tarda "
            "5-10 min (descarga ~356 MB) y esas consultas fallan mientras "
            "tanto -- reintenta en unos minutos. Cubren solo los últimos "
            "años cacheados, no el histórico completo desde 2008"
        ),
        (
            "Cuenca en Datos publica varios recursos como .ods (OpenDocument "
            "spreadsheet), formato que preview_resource_data todavía no "
            "soporta como tabla; usa download_resource para esos casos"
        ),
        (
            "SIPA es Ministerio de Agricultura, Ganadería y Pesca — distinto de "
            "MPCEIP (Producción/Comercio Exterior); get_archivo_seccion(fuente='sipa') "
            "solo devuelve metadata + URL directa, nunca el archivo (algunos "
            "superan 41 MB, muy por encima del tope de 5 MB de "
            "download_resource/preview_resource_data)"
        ),
    ],
}


def register_list_capabilities_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Describir las capacidades del servidor (alias)", annotations=READ_ONLY
    )
    @log_tool
    async def list_capabilities(
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Describe what this Ecuador MCP can do: sources, key tools, prompts and limits.

        Deprecated: the server's own `instructions` now cover the general
        orientation (sources, recommended entry points, prompts, format),
        and `ecuador://fuentes` is the structured, always-current source
        catalog. Kept as a compatibility alias for the per-tool "limites"
        notes not yet folded into `ecuador://fuentes`.

        Args:
            format: text | json
        """

        def to_text(data: dict) -> str:
            lines = [
                f"{data['name']} v{data['version']}",
                "",
                "Fuentes:",
                *[f"- {f}" for f in data["fuentes"]],
                "",
                "Entrada recomendada:",
                *[f"- {x}" for x in data["entrada"]],
                "",
                "Tools clave:",
            ]
            for group, tools in data["tools_clave"].items():
                lines.append(f"- {group}: {', '.join(tools)}")
            lines.extend(
                [
                    "",
                    "Resources:",
                    *[f"- {r}" for r in data["resources"]],
                    "",
                    data["format"],
                    "",
                    "Límites:",
                    *[f"- {x}" for x in data["limites"]],
                ]
            )
            return "\n".join(lines)

        return render_structured(_CAPABILITIES, format, text_builder=to_text)

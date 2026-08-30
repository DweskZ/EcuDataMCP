from mcp.server.fastmcp import FastMCP

from helpers.format_out import render_output
from helpers.logging import log_tool

_CAPABILITIES = {
    "name": "Ecuador MCP",
    "version": "0.8.2",
    "fuentes": [
        "CKAN datos abiertos (nacional, www.datosabiertos.gob.ec)",
        (
            "Cuenca en Datos (portal municipal CKAN independiente, "
            "source='cuenca' en los mismos tools CKAN)"
        ),
        "gob.ec trámites/instituciones/regulaciones",
        "SERCOP OCDS contratos",
        "SGR COE eventos de riesgo + SAT tsunami",
        "IG-EPN Instituto Geofísico (sismos)",
        "DPA provincias/cantones/parroquias (offline INEC)",
        "ANDA (NADA/IHSN) catálogo de encuestas y censos del INEC",
        "Ecuador en Cifras (INEC): boletines/metodología/series históricas por tema",
        "BCE (BCEData) catálogo estadístico: monetario, fiscal, externo, real",
        "Supercías directorio de compañías",
        "Supercías registro de auditores externos autorizados",
        "Supercías ranking financiero (últimos años, requiere build local)",
        (
            "SIPA (Ministerio de Agricultura, Ganadería y Pesca): series "
            "agropecuarias reales — precios, comercio exterior, crédito, "
            "producción, censos — organizadas en 4 módulos"
        ),
        (
            "Contraloría General del Estado: CSV trimestrales de informes de "
            "auditoría aprobados a cualquier institución pública del país"
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
        ],
        "tramites": [
            "search_tramites",
            "get_tramite_info",
            "list_instituciones",
            "get_institucion_info",
        ],
        "normas": ["search_regulaciones", "get_regulacion_info"],
        "compras": ["search_contratos", "get_contrato_info"],
        "riesgos": ["search_eventos_riesgo", "list_sat_tsunami", "search_sismos"],
        "geo": ["lookup_ubicacion"],
        "encuestas": ["search_anda", "get_anda_survey_info", "download_anda_microdata"],
        "inec_estadisticas": [
            "search_inec_estadisticas",
            "get_inec_estadistica_files",
            "search_inec_publicaciones",
            "get_inec_publicacion_archivos",
            "search_biinec_extras",
        ],
        "macro": [
            "search_indicadores_bce",
            "get_indicador_bce",
            "audit_bce_catalog",
            "search_bce_iem",
            "get_bce_iem_table",
        ],
        "companias": [
            "search_companias",
            "get_compania_info",
            "search_auditores",
            "get_auditor_info",
        ],
        "financieros": ["search_ranking", "get_financials"],
        "agropecuario": ["list_sipa_modulos", "get_sipa_modulo_archivos"],
        "auditoria": ["list_contraloria_informes", "get_contraloria_informe"],
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
            "grupos BCEData; no descarga todos los valores de todas las series. "
            "Usa get_indicador_bce para pedir los valores de un grupo, frecuencia "
            "y unidad concretos."
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
            "search_ranking/get_financials: requieren que el operador del "
            "servidor haya corrido scripts/build_supercias_financials_db.py "
            "de antemano (no se construye solo); cubren solo los últimos "
            "años cacheados, no el histórico completo desde 2008"
        ),
        (
            "Cuenca en Datos publica varios recursos como .ods (OpenDocument "
            "spreadsheet), formato que preview_resource_data todavía no "
            "soporta como tabla; usa download_resource para esos casos"
        ),
        (
            "SIPA es Ministerio de Agricultura, Ganadería y Pesca — distinto de "
            "MPCEIP (Producción/Comercio Exterior); get_sipa_modulo_archivos "
            "solo devuelve metadata + URL directa, nunca el archivo (algunos "
            "superan 41 MB, muy por encima del tope de 5 MB de "
            "download_resource/preview_resource_data)"
        ),
    ],
}


def register_list_capabilities_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_capabilities(format: str = "text") -> str:
        """
        Describe what this Ecuador MCP can do: sources, key tools, prompts and limits.

        Call this first when you are unsure which tool to use.

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

        return render_output(_CAPABILITIES, format, text_builder=to_text)

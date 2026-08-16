from mcp.server.fastmcp import FastMCP

from helpers.format_out import render_output
from helpers.logging import log_tool

_CAPABILITIES = {
    "name": "Ecuador MCP",
    "version": "0.5.2",
    "fuentes": [
        "CKAN datos abiertos",
        "gob.ec trámites/instituciones/regulaciones",
        "SERCOP OCDS contratos",
        "SGR COE eventos de riesgo + SAT tsunami",
        "IG-EPN Instituto Geofísico (sismos)",
        "DPA provincias/cantones/parroquias (offline INEC)",
        "ANDA (NADA/IHSN) catálogo de encuestas y censos del INEC",
        "BCE (BCEData) catálogo estadístico: monetario, fiscal, externo, real",
    ],
    "entrada": [
        "list_capabilities",
        "search_ecuador",
        "prompts: explorar_datos / consultar_tramite / investigar_contrato / buscar_regulacion / monitorear_riesgos",
    ],
    "tools_clave": {
        "datos": [
            "search_datasets",
            "query_resource_data",
            "preview_resource_data",
            "list_categories",
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
        "macro": ["search_indicadores_bce", "get_indicador_bce"],
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
            "grupos); no cubre inflación (CPI) ni pobreza de Ecuador, eso es "
            "INEC vía search_anda"
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

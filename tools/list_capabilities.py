from mcp.server.fastmcp import FastMCP

from helpers.logging import log_tool

_CAPABILITIES = """Ecuador MCP — capacidades del servidor

Fuentes:
- CKAN datos abiertos (www.datosabiertos.gob.ec): datasets, orgs, categorías, DataStore, preview CSV/JSON/XLSX
- gob.ec: trámites, instituciones, regulaciones (+ vínculo trámite→norma)
- SERCOP OCDS: contratos públicos (search + expediente por OCID)
- Referencia geográfica offline: 24 provincias (códigos INEC)

Entrada recomendada:
1) search_ecuador(query) para orientar
2) o un prompt MCP: explorar_datos / consultar_tramite / investigar_contrato / buscar_regulacion

Tools clave:
- Datos: search_datasets, get_dataset_info, list_dataset_resources, query_resource_data, preview_resource_data
- Trámites: search_tramites, get_tramite_info, list_instituciones, get_institucion_info
- Normas: search_regulaciones, get_regulacion_info
- Compras: search_contratos, get_contrato_info
- Geo: lookup_ubicacion
- Meta: list_capabilities

Resources MCP:
- ecuador://fuentes
- ecuador://provincias
- ecuador://instituciones-clave

Límites conocidos:
- Cert TLS del portal CKAN puede estar vencido (fallback allowlist + CKAN_INSECURE_TLS)
- SERCOP a veces responde 429 (reintentos + fallback de años)
- Búsqueda de trámites/regulaciones sin institution_id es parcial (API gob.ec)
"""


def register_list_capabilities_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_capabilities() -> str:
        """
        Describe what this Ecuador MCP can do: sources, key tools, prompts and limits.

        Call this first when you are unsure which tool to use.
        """
        return _CAPABILITIES.strip()

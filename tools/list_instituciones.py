from helpers import gobec_client
from helpers.logging import log_tool
from mcp.server.fastmcp import FastMCP


def register_list_instituciones_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_instituciones(query: str = "", page: int = 1) -> str:
        """
        List or search public institutions registered on Ecuador's gob.ec portal.

        If a query is provided, searches across all institutions by name or acronym.
        Without a query, returns a paginated list.

        Common institutions: SRI (ID: 8), Registro Civil (ID: 23), ANT (ID: 62),
        Cancillería (ID: 16), IESS (ID: 5), Ministerio de Salud, INEC, BCE.

        Args:
            query: Optional search term (e.g. "SRI", "salud", "rentas")
            page: Page number (1-based, default: 1, only used without query)
        """
        try:
            if query:
                instituciones = await gobec_client.find_institucion(query)
            else:
                api_page = max(page - 1, 0)
                instituciones = await gobec_client.list_instituciones(page=api_page)
        except Exception as e:
            return f"Error al listar instituciones: {e}"

        if not instituciones:
            msg = "No se encontraron instituciones"
            if query:
                msg += f" para: '{query}'"
            return msg

        parts = []
        if query:
            parts.append(f"Instituciones que coinciden con '{query}':")
        else:
            parts.append(f"Instituciones públicas del Ecuador (página {page}):")
        parts.append(f"Mostrando {min(len(instituciones), 30)} resultados\n")

        for i, inst in enumerate(instituciones[:30], 1):
            nombre = inst.get("institucion", inst.get("nombre", "Sin nombre"))
            siglas = inst.get("siglas", "")
            inst_id = inst.get("institucion_id", "?")

            label = f"{nombre} ({siglas})" if siglas else nombre
            parts.append(f"{i}. {label}")
            parts.append(f"   ID: {inst_id}")

            if inst.get("sector"):
                parts.append(f"   Sector: {inst['sector']}")
            if inst.get("website"):
                parts.append(f"   Web: {inst['website']}")
            if inst.get("url"):
                parts.append(f"   Portal: {inst['url']}")
            parts.append("")

        parts.append(
            "Tip: Usa search_tramites(institution_id='ID') para ver los trámites de una institución."
        )

        return "\n".join(parts)

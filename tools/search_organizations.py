from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.logging import log_tool


def register_search_organizations_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_organizations(
        query: str = "", page: int = 1, page_size: int = 20
    ) -> str:
        """
        Search for public institutions that publish data on Ecuador's open data portal.

        There are 98+ organizations including INEC, SRI, Ministerio de Salud, BCE, etc.

        Args:
            query: Optional search term (e.g. "salud", "SRI", "INEC")
            page: Page number (1-based, default: 1)
            page_size: Results per page (default: 20, max: 100)
        """
        offset = (max(page, 1) - 1) * page_size
        try:
            orgs = await ckan_client.list_organizations(
                query=query, limit=page_size, offset=offset
            )
        except Exception as e:
            return f"Error: {e}"

        if not orgs:
            msg = "No se encontraron organizaciones"
            if query:
                msg += f" para: '{query}'"
            return msg

        parts = []
        if query:
            parts.append(f"Organizaciones que coinciden con '{query}':\n")
        else:
            parts.append(f"Organizaciones (página {page}):\n")

        for i, org in enumerate(orgs, 1):
            parts.append(f"{i}. {org.get('title', org.get('display_name', 'Sin nombre'))}")
            parts.append(f"   ID: {org.get('name')}")
            parts.append(f"   Datasets: {org.get('package_count', 0)}")
            if org.get("description"):
                parts.append(f"   Descripción: {org['description'][:150]}")
            parts.append("")

        return "\n".join(parts)

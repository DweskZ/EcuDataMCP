from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.logging import log_tool


def register_list_categories_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_categories() -> str:
        """
        List all thematic categories of Ecuador's open data portal.

        Categories include: Salud, Educación, Economía y Finanzas, Seguridad y Defensa,
        Anticorrupción, Ambiente y Agua, Transporte, Turismo, and more.
        Each category shows the number of datasets it contains.

        Use the category 'name' field as the 'category' parameter in search_datasets
        to filter results by topic.
        """
        try:
            groups = await ckan_client.list_groups()
        except Exception as e:
            return f"Error: {e}"

        if not groups:
            return "No se encontraron categorías."

        total_datasets = sum(g.get("package_count", 0) for g in groups)
        parts = [
            "Categorías temáticas del portal de datos abiertos de Ecuador",
            f"Total: {len(groups)} categorías con {total_datasets} datasets\n",
        ]

        groups_sorted = sorted(groups, key=lambda g: g.get("package_count", 0), reverse=True)

        for i, g in enumerate(groups_sorted, 1):
            title = g.get("title", g.get("display_name", "Sin nombre"))
            name = g.get("name", "")
            count = g.get("package_count", 0)
            parts.append(f"{i}. {title} ({count} datasets)")
            parts.append(f"   ID para filtrar: {name}")
            parts.append("")

        parts.append(
            "Tip: Usa search_datasets(query='...', category='nombre_categoria') "
            "para filtrar datasets por categoría."
        )

        return "\n".join(parts)

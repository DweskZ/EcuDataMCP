from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.env_config import get_base_url
from helpers.logging import log_tool


def register_get_category_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_category_info(category: str, include_datasets: bool = True) -> str:
        """
        Get details for a thematic category (CKAN group) on Ecuador's open data portal.

        Use list_categories first to discover valid category IDs (the 'name' field,
        e.g. 'salud', 'educacion', 'economia-y-finanzas').

        Args:
            category: Category slug/name from list_categories
            include_datasets: Include sample datasets in the category (default True)
        """
        try:
            group = await ckan_client.get_group(
                category, include_datasets=include_datasets
            )
        except Exception as e:
            return f"Error al obtener categoría '{category}': {e}"

        title = group.get("title") or group.get("display_name") or category
        name = group.get("name", category)
        site = get_base_url("ckan_site").rstrip("/")
        parts = [
            f"Categoría: {title}",
            f"ID: {name}",
            f"Datasets: {group.get('package_count', 0)}",
            f"URL: {site}/group/{name}",
        ]

        description = (group.get("description") or "").strip()
        if description:
            parts.append("")
            parts.append(f"Descripción: {description[:800]}")

        packages = group.get("packages") or []
        if packages:
            parts.append("")
            parts.append(f"Datasets de ejemplo ({min(len(packages), 15)}):")
            for i, pkg in enumerate(packages[:15], 1):
                pkg_title = pkg.get("title") or pkg.get("name", "Sin título")
                pkg_name = pkg.get("name") or pkg.get("id", "")
                parts.append(f"{i}. {pkg_title}")
                parts.append(f"   ID: {pkg_name}")

        parts.append("")
        parts.append(
            f"Tip: Usa search_datasets(query='', category='{name}') para explorar más."
        )
        return "\n".join(parts)

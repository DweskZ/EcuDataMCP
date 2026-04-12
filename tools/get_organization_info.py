from mcp.server.fastmcp import FastMCP

from helpers import ckan_client, env_config
from helpers.logging import log_tool


def register_get_organization_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_organization_info(organization_id: str) -> str:
        """
        Get detailed information about a public institution and its published datasets.

        Returns the institution name, description, dataset count, and a list of its datasets.

        Args:
            organization_id: The organization slug (e.g. "sri-servicio-de-rentas-internas", "instituto-nacional-de-estadisticas-y-censos")
        """
        try:
            org = await ckan_client.get_organization(organization_id)
        except Exception as e:
            return f"Error: {e}"

        site = env_config.get_base_url("ckan_site")
        parts = [
            f"Organización: {org.get('title', 'Desconocida')}",
            "",
        ]

        if org.get("name"):
            parts.append(f"ID: {org['name']}")
            parts.append(f"URL: {site}organization/{org['name']}")
        if org.get("description"):
            parts.append(f"Descripción: {org['description'][:500]}")

        parts.append(f"Total de datasets: {org.get('package_count', 0)}")
        parts.append(f"Estado: {org.get('state', 'Desconocido')}")

        datasets = org.get("packages", [])
        if datasets:
            parts.append("")
            parts.append(f"Datasets publicados ({len(datasets)}):")
            for i, ds in enumerate(datasets[:25], 1):
                title = ds.get("title", ds.get("name", "Sin título"))
                parts.append(f"  {i}. {title}")
                parts.append(f"     ID: {ds.get('id', ds.get('name', ''))}")
            if len(datasets) > 25:
                parts.append(f"  ... y {len(datasets) - 25} más")

        return "\n".join(parts)

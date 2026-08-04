from mcp.server.fastmcp import FastMCP

from helpers import ckan_client, env_config
from helpers.logging import log_tool


def register_search_datasets_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_datasets(
        query: str, page: int = 1, page_size: int = 20, category: str = ""
    ) -> str:
        """
        Search for datasets on Ecuador's open data portal (www.datosabiertos.gob.ec).

        This is the starting point for exploring government data from 98+ public institutions.
        Use short, specific queries in Spanish for best results.

        Typical workflow: search_datasets → list_dataset_resources → preview_resource_data

        Args:
            query: Search keywords (e.g. "empleo", "salud", "presupuesto", "SRI recaudación")
            page: Page number (1-based, default: 1)
            page_size: Results per page (default: 20, max: 100)
            category: Optional category filter (e.g. "sal" for Salud, "edu" for Educación).
                      Use list_categories to see all available categories.
        """
        start = (max(page, 1) - 1) * page_size
        result = await ckan_client.search_datasets(
            query=query, rows=page_size, start=start, category=category
        )

        datasets = result.get("results", [])
        total = result.get("count", 0)

        if not datasets:
            return f"No se encontraron datasets para: '{query}'"

        site = env_config.get_base_url("ckan_site")
        parts = [
            f"Se encontraron {total} dataset(s) para: '{query}'",
            f"Página {page} (mostrando {len(datasets)} resultados):\n",
        ]

        for i, ds in enumerate(datasets, 1):
            parts.append(f"{i}. {ds.get('title', 'Sin título')}")
            parts.append(f"   ID: {ds.get('id')}")

            notes = ds.get("notes", "")
            if notes:
                parts.append(f"   Descripción: {notes[:200]}...")

            org = ds.get("organization")
            if org and isinstance(org, dict):
                parts.append(f"   Organización: {org.get('title', '')}")

            tags = ds.get("tags", [])
            if tags:
                tag_names = [t.get("display_name", t.get("name", "")) for t in tags[:5]]
                parts.append(f"   Tags: {', '.join(tag_names)}")

            num_res = ds.get("num_resources", len(ds.get("resources", [])))
            parts.append(f"   Recursos: {num_res}")

            slug = ds.get("name", ds.get("id", ""))
            parts.append(f"   URL: {site}dataset/{slug}")
            parts.append("")

        return "\n".join(parts)

from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_category_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_category_info(
        category: str,
        include_datasets: bool = True,
        source: str = "nacional",
        format: str = "text",
    ) -> str:
        """
        Get details for a thematic category (CKAN group) on Ecuador's open data portal.

        Use list_categories first to discover valid category IDs (the 'name' field,
        e.g. 'salud', 'educacion', 'economia-y-finanzas').

        Args:
            category: Category slug/name from list_categories
            include_datasets: Include sample datasets in the category (default True)
            source: "nacional" (default), "cuenca" (Cuenca municipal portal), or
                    "latacunga" (Latacunga municipal portal)
            format: text | json
        """
        try:
            group = await ckan_client.get_group(
                category, include_datasets=include_datasets, source=source
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "category": category},
                format,
                text_builder=lambda d: (
                    f"Error al obtener categoría '{d['category']}': {d['error']}"
                ),
            )

        title = group.get("title") or group.get("display_name") or category
        name = group.get("name", category)
        site = ckan_client.site_url(source).rstrip("/")
        packages = group.get("packages") or []
        payload = {
            "name": name,
            "title": title,
            "package_count": group.get("package_count", 0),
            "url": f"{site}/group/{name}",
            "description": (group.get("description") or "").strip() or None,
            "datasets": [
                {
                    "id": pkg.get("name") or pkg.get("id", ""),
                    "title": pkg.get("title") or pkg.get("name") or "Sin título",
                }
                for pkg in packages[:15]
            ],
        }

        def to_text(data: dict) -> str:
            parts = [
                f"Categoría: {data['title']}",
                f"ID: {data['name']}",
                f"Datasets: {data.get('package_count', 0)}",
                f"URL: {data['url']}",
            ]
            if data.get("description"):
                parts.append("")
                parts.append(f"Descripción: {str(data['description'])[:800]}")
            if data.get("datasets"):
                parts.append("")
                parts.append(f"Datasets de ejemplo ({len(data['datasets'])}):")
                for i, pkg in enumerate(data["datasets"], 1):
                    parts.append(f"{i}. {pkg['title']}")
                    parts.append(f"   ID: {pkg.get('id', '')}")
            parts.append("")
            parts.append(
                f"Tip: Usa search_datasets(query='', category='{data['name']}') "
                "para explorar más."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

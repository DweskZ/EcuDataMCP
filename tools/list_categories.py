from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_categories_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_categories(format: str = "text") -> str:
        """
        List all thematic categories of Ecuador's open data portal.

        Categories include: Salud, Educación, Economía y Finanzas, Seguridad y Defensa,
        Anticorrupción, Ambiente y Agua, Transporte, Turismo, and more.
        Each category shows the number of datasets it contains.

        Use the category 'name' field as the 'category' parameter in search_datasets
        to filter results by topic.

        Args:
            format: text | json
        """
        try:
            groups = await ckan_client.list_groups()
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        groups_sorted = sorted(
            groups, key=lambda g: g.get("package_count", 0), reverse=True
        )
        payload = {
            "total": len(groups_sorted),
            "total_datasets": sum(g.get("package_count", 0) for g in groups_sorted),
            "categories": [
                {
                    "name": g.get("name", ""),
                    "title": g.get("title") or g.get("display_name") or "Sin nombre",
                    "package_count": g.get("package_count", 0),
                }
                for g in groups_sorted
            ],
        }

        if not groups_sorted:
            return render_output(
                payload,
                format,
                text_builder=lambda _: "No se encontraron categorías.",
            )

        def to_text(data: dict) -> str:
            parts = [
                "Categorías temáticas del portal de datos abiertos de Ecuador",
                f"Total: {data['total']} categorías con {data['total_datasets']} datasets\n",
            ]
            for i, g in enumerate(data["categories"], 1):
                parts.append(f"{i}. {g['title']} ({g['package_count']} datasets)")
                parts.append(f"   ID para filtrar: {g['name']}")
                parts.append("")
            parts.append(
                "Tip: Usa search_datasets(query='...', category='nombre_categoria') "
                "para filtrar datasets por categoría."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

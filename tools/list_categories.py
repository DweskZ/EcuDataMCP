from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import ckan_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_list_categories_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Listar categorías temáticas", annotations=READ_ONLY)
    @log_tool
    async def list_categories(
        source: ckan_client.CkanSource = "nacional",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        List all thematic categories of Ecuador's open data portal.

        Categories include: Salud, Educación, Economía y Finanzas, Seguridad y Defensa,
        Anticorrupción, Ambiente y Agua, Transporte, Turismo, and more.
        Each category shows the number of datasets it contains.

        Use the category 'name' field as the 'category' parameter in search_datasets
        to filter results by topic.

        Args:
            source: "nacional" (default), "cuenca" (Cuenca municipal portal),
                    "latacunga" (Latacunga municipal portal), or "iadb" (IADB's
                    open-data portal, data.iadb.org — NOT Ecuador-only, a
                    regional/global catalog)
            format: text | json
        """
        try:
            groups = await ckan_client.list_groups(source=source)
        except Exception as e:
            raise ToolError(f"Error: {e}") from e

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
            # Legitimate empty result (zero categories found), not a failure.
            return render_structured(
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

        return render_structured(payload, format, text_builder=to_text)

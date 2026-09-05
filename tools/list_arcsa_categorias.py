from mcp.server.fastmcp import FastMCP

from helpers import arcsa_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_arcsa_categorias_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_arcsa_categorias(format: str = "text") -> str:
        """
        List ARCSA's "Base de Registros Emitidos" categories
        (controlsanitario.gob.ec/base-de-datos/) — the sanitary registry
        for food, medications, cosmetics, medical devices, natural
        products, pesticides, and related establishments/permits, 27
        top-level categories with 77 documents total.

        This is a DIFFERENT source from search_datasets/get_dataset_info
        for the ARCSA CKAN organization: this page is the live registry
        (current authorizations/notifications), the CKAN datasets only
        cover suspended/cancelled records.

        A few categories nest further sub-categories (e.g. by year) —
        those show up as each document's "subgrupo" from
        get_arcsa_categoria_archivos, not as separate entries here. Two
        categories are currently empty (0 archivos) but still listed,
        since they're a genuine part of the page's own structure.

        Args:
            format: text | json
        """
        result = await arcsa_client.list_categorias()

        def to_text(data: dict) -> str:
            categorias = data.get("categorias") or []
            parts = [
                f"ARCSA Base de Registros Emitidos — {data['total']} categoría(s):",
                "",
            ]
            for c in categorias:
                parts.append(
                    f"- {c['id']}: {c['nombre']} ({c['total_archivos']} archivo(s))"
                )
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

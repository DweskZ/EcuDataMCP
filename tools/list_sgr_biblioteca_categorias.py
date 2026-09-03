from mcp.server.fastmcp import FastMCP

from helpers import sgr_publicaciones_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_sgr_biblioteca_categorias_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_sgr_biblioteca_categorias(format: str = "text") -> str:
        """
        List SGR's Biblioteca document-library categories
        (gestionderiesgos.gob.ec/biblioteca/) — resolutions, contingency
        plans, threat maps, tsunami evacuation routes, and more, ~1660
        documents across 19 top-level categories.

        This is a DIFFERENT source from search_eventos_riesgo /
        search_sgr_sitreps: a standing document library, not event
        reports. Several categories nest further sub-categories (e.g. by
        province or place) — those show up as each document's "subgrupo"
        from get_sgr_biblioteca_categoria_archivos, not as separate
        entries here.

        IMPORTANT: a real share of Biblioteca's links 404 (confirmed live
        across several categories, not correlated with a clean id range or
        category) — treat this as a candidate catalog of what the page
        lists, not a guarantee every document resolves. Format is also
        reported as unknown for every entry (the download link carries no
        file extension).

        Args:
            format: text | json
        """
        result = await sgr_publicaciones_client.list_biblioteca_categorias()

        def to_text(data: dict) -> str:
            categorias = data.get("categorias") or []
            parts = [f"SGR Biblioteca — {data['total']} categoría(s):", ""]
            for c in categorias:
                parts.append(f"- {c['id']}: {c['nombre']} ({c['total_archivos']} archivo(s))")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

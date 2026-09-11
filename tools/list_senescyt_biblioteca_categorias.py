from mcp.server.mcpserver import MCPServer

from helpers import senescyt_biblioteca_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_senescyt_biblioteca_categorias_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def list_senescyt_biblioteca_categorias(format: str = "text") -> str:
        """
        List the Viceministerio de Educación Superior's Biblioteca
        document-library categories (educacion.gob.ec/edusuperior/biblioteca/)
        — PAC por año, normativa LOES/SNNA, acuerdos institucionales (back to
        at least 2015), exámenes especiales/auditoría, indicadores ACTI, and
        more; ~1,259 documents across 17 top-level categories.

        This is a DIFFERENT source from search_senescyt_estadisticas (a
        small, 12-entry curated report archive on siau.senescyt.gob.ec) and
        search_minedec_matricula (basic-education enrollment, same
        educacion.gob.ec domain but a plain page, not this library). Several
        categories nest sub-categories several levels deep (e.g. Normativa >
        Reglamento de Servicios de Registro de Títulos > Documento inicial)
        — get_senescyt_biblioteca_categoria_archivos surfaces only the
        nearest nested header as each document's "subgrupo", not a full
        breadcrumb. Format is also reported as unknown for every entry (the
        download link carries no file extension).

        Args:
            format: text | json
        """
        result = await senescyt_biblioteca_client.list_biblioteca_categorias()

        def to_text(data: dict) -> str:
            categorias = data.get("categorias") or []
            parts = [
                f"Biblioteca Educación Superior (SENESCYT/MINEDEC) — {data['total']} categoría(s):",
                "",
            ]
            for c in categorias:
                parts.append(f"- {c['id']}: {c['nombre']} ({c['total_archivos']} archivo(s))")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

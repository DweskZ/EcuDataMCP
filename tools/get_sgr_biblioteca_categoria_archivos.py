from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import sgr_publicaciones_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_sgr_biblioteca_categoria_archivos_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Ver archivos de una categoría de la Biblioteca SGR", annotations=READ_ONLY)
    @log_tool
    async def get_sgr_biblioteca_categoria_archivos(
        categoria: str, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        List one SGR Biblioteca top-level category's documents.

        Get categoria (an id or nombre) from
        list_sgr_biblioteca_categorias. Returns each document's subgrupo
        (nested sub-category, e.g. a province name, when the category
        nests one — None otherwise), titulo, id, and direct URL. Format
        is reported as "DESCONOCIDO": the download link carries no file
        extension, and per-entry verification isn't feasible at this
        scale — a live sample confirmed PDF, but expect other types (e.g.
        map images) among the "Mapas de..." categories. Some links 404
        instead of serving a file (confirmed live, not correlated with a
        clean id range or category) — this is a candidate catalog of what
        the page lists, not a guarantee every document resolves.

        Args:
            categoria: A category "id" or "nombre" from
                list_sgr_biblioteca_categorias (nombre match is
                accent/case-insensitive).
            format: text | json
        """
        try:
            result = await sgr_publicaciones_client.get_biblioteca_categoria_archivos(categoria)
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(
                f"Error al obtener la categoría de Biblioteca SGR: {e}"
            ) from e

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [f"SGR Biblioteca — {data.get('nombre')} ({data.get('id')})", ""]
            if not archivos:
                parts.append("No se encontraron archivos en esta categoría.")
                return "\n".join(parts)
            parts.append(f"{data['total']} archivo(s):")
            for a in archivos:
                etiqueta = " / ".join(p for p in (a.get("subgrupo"), a.get("titulo")) if p)
                parts.append(f"- {etiqueta} [{a.get('formato')}]")
                parts.append(f"   {a.get('url')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

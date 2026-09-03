from mcp.server.fastmcp import FastMCP

from helpers import sgr_publicaciones_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_sgr_biblioteca_categoria_archivos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_sgr_biblioteca_categoria_archivos(categoria: str, format: str = "text") -> str:
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
            return render_output(
                {"error": str(e), "categoria": categoria},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "categoria": categoria},
                format,
                text_builder=lambda d: (
                    f"Error al obtener la categoría de Biblioteca SGR: {d['error']}"
                ),
            )

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

        return render_output(result, format, text_builder=to_text)

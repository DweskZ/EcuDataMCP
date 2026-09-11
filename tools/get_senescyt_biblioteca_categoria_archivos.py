from mcp.server.mcpserver import MCPServer

from helpers import senescyt_biblioteca_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_senescyt_biblioteca_categoria_archivos_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def get_senescyt_biblioteca_categoria_archivos(
        categoria: str, format: str = "text"
    ) -> str:
        """
        List one Biblioteca (educacion.gob.ec/edusuperior/biblioteca/) top-
        level category's documents.

        Get categoria (an id or nombre) from
        list_senescyt_biblioteca_categorias. Returns each document's
        subgrupo (nearest nested sub-category header, when the category
        nests one — None otherwise; some categories nest several levels
        deep, in which case subgrupo is only the innermost header, not a
        full breadcrumb), titulo, id, and direct URL. Format is reported as
        "DESCONOCIDO": the download link carries no file extension, and
        per-entry verification isn't feasible at this scale (a live sample
        confirmed a real PDF behind one link).

        Args:
            categoria: A category "id" or "nombre" from
                list_senescyt_biblioteca_categorias (nombre match is
                accent/case-insensitive).
            format: text | json
        """
        try:
            result = await senescyt_biblioteca_client.get_biblioteca_categoria_archivos(categoria)
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
                    f"Error al obtener la categoría de la Biblioteca de Educación "
                    f"Superior: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [f"Biblioteca Educación Superior — {data.get('nombre')} ({data.get('id')})", ""]
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

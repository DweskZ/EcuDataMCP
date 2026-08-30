from mcp.server.fastmcp import FastMCP

from helpers import inec_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_inec_publicacion_archivos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_inec_publicacion_archivos(post: str, format: str = "text") -> str:
        """
        List the direct file links (PDF/XLSX/CSV/ZIP) embedded in one INEC
        publication found via search_inec_publicaciones.

        Args:
            post: Either the numeric "id" from search_inec_publicaciones, or
                the publication's full ecuadorencifras.gob.ec URL.
            format: text | json
        """
        identifier: int | str = int(post) if post.strip().isdigit() else post
        try:
            result = await inec_client.get_publicacion_files(identifier)
        except ValueError as e:
            return render_output(
                {"error": str(e), "post": post},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "post": post},
                format,
                text_builder=lambda d: f"Error al obtener la publicación: {d['error']}",
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            fechas = (
                f"Publicado: {data.get('fecha_publicacion')} · "
                f"Modificado: {data.get('fecha_modificacion')}"
            )
            parts = [
                f"Publicación: {data.get('titulo')}",
                fechas,
                f"URL: {data.get('url')}",
                "",
            ]
            if not archivos:
                parts.append("No se encontraron archivos descargables en esta publicación.")
                return "\n".join(parts)
            parts.append(f"{len(archivos)} archivo(s):")
            for i, f in enumerate(archivos, 1):
                parts.append(f"{i}. {f.get('label')} [{f.get('format')}]")
                parts.append(f"   {f.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

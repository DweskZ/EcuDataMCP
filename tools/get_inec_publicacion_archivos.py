from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import inec_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.result_types import ResultadoArchivos
from helpers.tool_meta import READ_ONLY


def register_get_inec_publicacion_archivos_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Ver archivos de una publicación del INEC",
        description=(
            "File links (PDF/XLSX/CSV/ZIP) in one INEC publication (id or URL from "
            "search_inec_publicaciones). For a ZIP, next: list_zip_contents, "
            "then read_zip_member."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_inec_publicacion_archivos(
        post: str, format: Literal["text", "json"] = "text"
    ) -> Annotated[CallToolResult, ResultadoArchivos]:
        """
        List the direct file links (PDF/XLSX/CSV/ZIP) embedded in one INEC
        publication found via search_inec_publicaciones. For a .zip link,
        list_zip_contents shows its files and read_zip_member reads one of
        them as a table without downloading the archive.

        Args:
            post: Either the numeric "id" from search_inec_publicaciones, or
                the publication's full ecuadorencifras.gob.ec URL.
            format: text | json
        """
        identifier: int | str = int(post) if post.strip().isdigit() else post
        try:
            result = await inec_client.get_publicacion_files(identifier)
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Error al obtener la publicación: {e}") from e

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
            if any((f.get("format") or "").upper() == "ZIP" for f in archivos):
                parts.append("")
                parts.append(
                    "Para un .zip: list_zip_contents(url) muestra sus archivos y "
                    "read_zip_member(url, member) lee uno como tabla sin bajar el .zip."
                )
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

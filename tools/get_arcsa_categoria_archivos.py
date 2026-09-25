from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import arcsa_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_arcsa_categoria_archivos_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Ver archivos de una categoría de ARCSA", annotations=READ_ONLY)
    @log_tool
    async def get_arcsa_categoria_archivos(
        categoria: str, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        List one ARCSA "Base de Registros Emitidos" category's documents.

        Get categoria (an id or nombre) from list_arcsa_categorias. Returns
        each document's subgrupo (nested sub-category, e.g. a year, when
        the category nests one — None otherwise), titulo, id, and direct
        URL. Format is reported as "DESCONOCIDO": the download link
        carries no file extension (a spot check confirmed real files
        behind it, e.g. a PDF listado).

        Args:
            categoria: A category "id" or "nombre" from
                list_arcsa_categorias (nombre match is
                accent/case-insensitive).
            format: text | json
        """
        try:
            result = await arcsa_client.get_categoria_archivos(categoria)
        except ValueError as e:
            raise ToolError(f"Error: {e}") from e
        except Exception as e:
            raise ToolError(f"Error al obtener la categoría de ARCSA: {e}") from e

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [f"ARCSA — {data.get('nombre')} ({data.get('id')})", ""]
            if not archivos:
                parts.append("No se encontraron archivos en esta categoría.")
                return "\n".join(parts)
            parts.append(f"{data['total']} archivo(s):")
            for a in archivos:
                etiqueta = " / ".join(
                    p for p in (a.get("subgrupo"), a.get("titulo")) if p
                )
                parts.append(f"- {etiqueta} [{a.get('formato')}]")
                parts.append(f"   {a.get('url')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import inec_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_inec_estadistica_files_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Ver archivos de un tema estadístico del INEC", annotations=READ_ONLY)
    @log_tool
    async def get_inec_estadistica_files(
        url: str, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        List the direct file links published on one INEC statistical topic page.

        Get the url from search_inec_estadisticas. Returns technical bulletins,
        methodology, and historical series as direct PDF/XLSX/CSV/ZIP links —
        not the file contents. Use read_pdf on a .pdf link, or download it
        yourself for tabular formats.

        Args:
            url: A topic URL from search_inec_estadisticas's "url" field
                (must be on ecuadorencifras.gob.ec)
            format: text | json
        """
        try:
            result = await inec_client.get_topic_files(url)
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Error al obtener la página del tema: {e}") from e

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [f"Tema: {data.get('titulo')}", f"URL: {data.get('url')}", ""]
            if not archivos:
                parts.append("No se encontraron archivos descargables en esta página.")
                return "\n".join(parts)
            parts.append(f"{len(archivos)} archivo(s):")
            for i, f in enumerate(archivos, 1):
                parts.append(f"{i}. {f.get('label')} [{f.get('format')}]")
                parts.append(f"   {f.get('url')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import bce_indices_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_bce_indice_archivo_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Ver archivos de un índice de publicaciones del BCE", annotations=READ_ONLY)
    @log_tool
    async def get_bce_indice_archivo(
        pagina_id: str,
        anio: int = 0,
        max_archivos: int = 30,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Read the file archive for one BCE "índice" page (from search_bce_indices).

        Each item is one published file: year, period label (a quarter,
        month, or week number), a Spanish date when the source gives one
        (weekly series only), direct URL, and format.

        Args:
            pagina_id: The page's slug, from search_bce_indices' `pagina_id`
                field (e.g. "boletin-analitico-del-sector-petrolero-indice").
            anio: Restrict to one calendar year. 0 returns all years found.
            max_archivos: Cap on returned files (most recent years first),
                1-200. Use `anio` to reach further back than the cap allows.
            format: text | json
        """
        try:
            result = await bce_indices_client.get_archivo(
                pagina_id=pagina_id, anio=anio, max_archivos=max_archivos
            )
        except Exception as e:
            raise ToolError(
                f"Error al leer el índice '{pagina_id}' del BCE: {e}"
            ) from e

        def to_text(data: dict) -> str:
            pagina = data.get("pagina") or {}
            archivos = data.get("archivos") or []
            parts = [
                f"{pagina.get('titulo')} ({pagina.get('cadencia') or '?'})",
                (
                    f"{data['archivos_mostrados']} de {data['total_archivos']} archivo(s)"
                    + (" [truncado]" if data.get("truncado") else "")
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin archivos para ese filtro.")
                return "\n".join(parts)
            for a in archivos:
                fecha = f" — {a['fecha_texto']}" if a.get("fecha_texto") else ""
                parts.append(f"{a['anio']} {a['periodo']}{fecha} [{a['formato']}]")
                parts.append(f"   {a['url']}")
            parts.append("")
            parts.append(f"Fuente: {pagina.get('url')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import msp_gacetas_inmunoprevenibles_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_search_gacetas_inmunoprevenibles_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Buscar gacetas epidemiológicas de inmunoprevenibles", annotations=READ_ONLY)
    @log_tool
    async def search_gacetas_inmunoprevenibles(
        query: str = "", format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        List MSP's (Ministerio de Salud Pública) weekly vaccine-preventable-
        disease epidemiological gazettes ("Gaceta de Inmunoprevenibles",
        Semana Epidemiológica bulletins) — 2019 through the current week,
        362 PDFs confirmed live. Page discovery is dynamic (via MSP's
        WordPress REST API), so new weeks/years surface automatically.

        Since 2024 some weeks ship a disease-specific companion report
        alongside the general bulletin (confirmed: tosferina/whooping
        cough) — each entry's "tipo" distinguishes "general" from that.
        This is one of several parallel MSP weekly gazette series
        (vectoriales, enfermedades de la piel/reemergentes, indicadores
        exist too but aren't covered by this tool).

        Args:
            query: Free text matched (accent-insensitive) against the
                file's titulo, anio, semana, or tipo
                ("general"/"tosferina"). Empty returns all files.
            format: text | json
        """
        try:
            result = await msp_gacetas_inmunoprevenibles_client.search_gacetas_inmunoprevenibles(
                query=query
            )
        except Exception as e:
            raise ToolError(
                f"Error al consultar las Gacetas de Inmunoprevenibles del MSP: {e}"
            ) from e

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"MSP — Gacetas de Inmunoprevenibles — {data['total']} resultado(s) de "
                    f"{data['total_en_archivo']} archivos"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, a in enumerate(archivos[:100], 1):
                semana = f"SE-{a['semana']}" if a.get("semana") else "SE desconocida"
                parts.append(f"{i}. {a['titulo']} [{a['anio']}-{a['mes']}, {semana}, {a['tipo']}]")
                parts.append(f"   {a['url']}")
            if len(archivos) > 100:
                parts.append(f"... y {len(archivos) - 100} más (usa query para acotar, o format=json)")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

from mcp.server.fastmcp import FastMCP

from helpers import superbancos_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_superbancos_secciones_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_superbancos_secciones(format: str = "text") -> str:
        """
        List the Superintendencia de Bancos statistics sections
        (superbancos.gob.ec/estadisticas/portalestudios/).

        Superbancos has no CKAN organization and no "datos abiertos"
        section, so this is the only path to its published statistics:
        monthly financial bulletins, cards/ATMs/correspondents service
        statistics, comparative annual bank behavior, and the publication
        calendar.

        IMPORTANT: each section page also embeds a client-side OneDrive
        widget that lazy-loads the *most recent* years' files outside the
        page HTML — not covered here. This tool only returns what is in
        the page's static archive tables, which for most sections stops
        around 2020-2021 (boletines financieros: 1997-2008 only). Follow
        up with get_superbancos_seccion_archivos(seccion) for one
        section's actual file listing and coverage.

        Args:
            format: text | json
        """
        secciones = superbancos_client.list_secciones()

        def to_text(data: list[dict]) -> str:
            parts = [f"Secciones de estadísticas Superbancos — {len(data)} sección(es):", ""]
            for s in data:
                parts.append(f"- {s['seccion']}: {s['nombre']}")
                parts.append(f"  {s['url']}")
            return "\n".join(parts)

        return render_output(secciones, format, text_builder=to_text)

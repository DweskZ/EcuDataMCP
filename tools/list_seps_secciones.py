from mcp.server.fastmcp import FastMCP

from helpers import seps_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_seps_secciones_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_seps_secciones(format: str = "text") -> str:
        """
        List the SEPS (Superintendencia de Economía Popular y Solidaria)
        statistics sections (estadisticas.seps.gob.ec).

        SEPS' main site (seps.gob.ec) actively blocks automated
        connections, but this statistics subdomain is a normal WordPress
        site and has no CKAN organization, so this is the only path to
        its published data: 22 sections on "Estadísticas SFPS" (Sector
        Financiero Popular y Solidario -- cooperatives, mutualistas,
        cajas: financial statements, deposits, credit portfolio, interest
        rates, financial inclusion, and risk ratings) plus 4 on
        "Estadísticas EPS" (non-financial popular/solidarity-economy
        organizations).

        Includes sfps_reportes_calificacion_de_riesgos: risk-rating
        bulletins (PDF) issued by SEPS-authorized rating agencies for
        SFPS entities, one per year 2020-2025 plus a 2026 Q1 cut.

        Follow up with get_seps_seccion_archivos(seccion) for one
        section's actual file listing.

        Args:
            format: text | json
        """
        secciones = seps_client.list_secciones()

        def to_text(data: list[dict]) -> str:
            parts = [f"Secciones de estadísticas SEPS — {len(data)} sección(es):", ""]
            for s in data:
                parts.append(f"- {s['seccion']}: {s['nombre']}")
                parts.append(f"  {s['url']}")
            return "\n".join(parts)

        return render_output(secciones, format, text_builder=to_text)

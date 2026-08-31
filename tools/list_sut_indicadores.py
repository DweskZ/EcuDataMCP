from mcp.server.fastmcp import FastMCP

from helpers import sut_powerbi_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_sut_indicadores_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_sut_indicadores(format: str = "text") -> str:
        """
        List the Ministerio del Trabajo/SUT's public Power BI "Indicadores"
        dashboards (sut.trabajo.gob.ec/mrl/contenido/indicadores/*.xhtml).

        These are live queryable semantic models, not static files — they
        cover monthly contract registrations by industry/province/gender
        since 2015 (contratos), employer-reported labor demand and skills
        gaps, training/certification stats, provincial employment-gap
        indicators, and a gender/workplace-policy compliance dashboard
        (PEA, wage gaps, lactation rooms, childcare, teleworking). None of
        this overlaps with what's already covered by CKAN's
        ministerio-del-trabajo datasets, which are current-snapshot-only.

        Follow up with get_sut_indicador_schema(indicador) to see one
        dashboard's queryable fields, then query_sut_indicador to pull
        actual data — any combination of fields, not just what one chart
        already shows.

        Args:
            format: text | json
        """
        indicadores = sut_powerbi_client.list_indicadores()

        def to_text(data: list[dict]) -> str:
            parts = [f"Indicadores SUT (Power BI) — {len(data)} dashboard(s):", ""]
            for i in data:
                parts.append(f"- {i['indicador']}: {i['nombre']}")
            return "\n".join(parts)

        return render_output(indicadores, format, text_builder=to_text)

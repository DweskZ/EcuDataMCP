from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from helpers import sut_powerbi_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_list_sut_indicadores_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Listar tableros de indicadores del SUT", annotations=READ_ONLY)
    @log_tool
    async def list_sut_indicadores(format: Literal["text", "json"] = "text") -> dict[str, Any]:
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
        payload = {"total": len(indicadores), "indicadores": indicadores}

        def to_text(data: dict) -> str:
            rows = data["indicadores"]
            parts = [f"Indicadores SUT (Power BI) — {len(rows)} dashboard(s):", ""]
            for i in rows:
                parts.append(f"- {i['indicador']}: {i['nombre']}")
            return "\n".join(parts)

        return render_structured(payload, format, text_builder=to_text)

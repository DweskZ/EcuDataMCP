from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import sut_powerbi_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_sut_indicador_schema_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Ver campos de un indicador del SUT o la Judicatura",
        description=(
            "Queryable fields of one SUT or Judicatura dashboard (fuente): columns, "
            "measures ([medida]/[suma]/[promedio]) and date levels, for query_sut_indicador."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_sut_indicador_schema(
        indicador: str,
        fuente: Literal["sut", "judicatura"] = "sut",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        List the queryable columns/measures/date-levels for one SUT
        Power BI dashboard, discovered from the report's own layout
        definition (every visual's underlying query), not by guessing.

        A field like "public contratos.nombre_padre_activ_econ_empresa"
        is a plain column usable in query_sut_indicador's campos or
        filtros; one ending in "[medida]" is an aggregate measure (only
        valid in campos, never filtros); one ending in "[Año]"/"[Mes]"
        is a date-hierarchy level.

        denuncias_publico and encuentra_empleo use an older report layout
        where visuals don't expose their query this way at all — their
        fields come from a small manually-captured set instead (recovered
        by driving the live dashboard and reading the queries it actually
        sent), not from this automatic discovery, but they show up here
        the same as any other field.

        Judicatura dashboards (fuente="judicatura") expose aggregate fields
        as "[suma]"/"[promedio]" (e.g. "CUB EST_CUB_AUDIENCIAS.Contador
        [suma]"); they are valid only in campos, like "[medida]" fields.

        Args:
            indicador: A key from list_catalogo(fuente=<fuente>).
            fuente: sut (default) | judicatura
            format: text | json
        """
        try:
            result = await sut_powerbi_client.get_indicador_schema(indicador, fuente)
        except ValueError as e:
            raise ToolError(str(e)) from e

        def to_text(data: dict) -> str:
            campos = data.get("campos") or []
            parts = [f"Indicador {data.get('fuente', 'sut')}: {data.get('nombre')}", ""]
            if not campos:
                parts.append("No se encontraron campos para este indicador.")
                return "\n".join(parts)
            parts.append(f"{len(campos)} campo(s):")
            for c in campos:
                parts.append(f"- {c}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

from mcp.server.fastmcp import FastMCP

from helpers import sut_powerbi_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_sut_indicador_schema_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_sut_indicador_schema(indicador: str, format: str = "text") -> str:
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

        Args:
            indicador: A key from list_sut_indicadores.
            format: text | json
        """
        try:
            result = await sut_powerbi_client.get_indicador_schema(indicador)
        except ValueError as e:
            return render_output(
                {"error": str(e), "indicador": indicador},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        def to_text(data: dict) -> str:
            campos = data.get("campos") or []
            parts = [f"Indicador SUT: {data.get('nombre')}", ""]
            if not campos:
                parts.append("No se encontraron campos para este indicador.")
                return "\n".join(parts)
            parts.append(f"{len(campos)} campo(s):")
            for c in campos:
                parts.append(f"- {c}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

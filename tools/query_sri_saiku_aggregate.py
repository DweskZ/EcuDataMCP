import json

from mcp.server.fastmcp import FastMCP

from helpers import sri_saiku_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_query_sri_saiku_aggregate_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def query_sri_saiku_aggregate(
        cube_id: str,
        row_dimension: str,
        row_hierarchy: str,
        row_level: str,
        measure: str,
        limit: int = 25,
        format: str = "text",
    ) -> str:
        """
        Ejecutar una consulta agregada y limitada en un cubo público de Saiku.

        La consulta tiene una sola dimensión en filas y una medida. El cubo,
        dimensión, jerarquía, nivel y medida deben salir de
        list_sri_saiku_cubes/describe_sri_saiku_cube. El límite máximo es 100.
        No acepta MDX arbitrario, no hace drill-through y no busca RUCs.

        Args:
            cube_id: Identificador completo del cubo
            row_dimension: Nombre de la dimensión para las filas
            row_hierarchy: Nombre de la jerarquía
            row_level: Nivel que se mostrará en las filas
            measure: Medida agregada
            limit: Máximo de filas solicitado (1-100)
            format: text | json
        """
        bounded_limit = min(max(int(limit), 1), 100)
        try:
            data = await sri_saiku_client.query_aggregate(
                cube_identifier=cube_id,
                row_dimension=row_dimension,
                row_hierarchy=row_hierarchy,
                row_level=row_level,
                measure=measure,
                limit=bounded_limit,
            )
        except Exception as exc:
            return render_output(
                {"error": str(exc), "cube_id": cube_id},
                format,
                text_builder=lambda result: (
                    f"Error al ejecutar la consulta agregada en Saiku: "
                    f"{result['error']}"
                ),
            )

        def to_text(result: dict) -> str:
            request = result["request"]
            parts = [
                "Resultado agregado de Saiku — SRI",
                f"Cubo: {result['cube'].get('cube')}",
                f"Filas: {request['row_dimension']} / {request['row_hierarchy']} / {request['row_level']}",
                f"Medida: {request['measure']}",
                f"Límite solicitado: {request['limit']}",
                "",
                json.dumps(result.get("result"), ensure_ascii=False, indent=2, default=str),
                "",
                f"Fuente: {result['source']}",
            ]
            return "\n".join(parts)

        return render_output(data, format, text_builder=to_text)

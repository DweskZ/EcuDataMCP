from mcp.server.fastmcp import FastMCP

from helpers import sri_saiku_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_sri_saiku_cubes_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_sri_saiku_cubes(format: str = "text") -> str:
        """
        Listar los cubos OLAP visibles en la instancia pública de Saiku del SRI.

        Esta herramienta solo consulta la sesión anónima y la ruta pública de
        descubrimiento. No lee la configuración administrativa ni devuelve
        registros de contribuyentes.

        Args:
            format: text | json
        """
        try:
            data = await sri_saiku_client.list_cubes()
        except Exception as exc:
            return render_output(
                {"error": str(exc), "source": sri_saiku_client.SRI_SAIKU_DISCOVER_URL},
                format,
                text_builder=lambda result: (
                    f"Error al descubrir los cubos Saiku del SRI: {result['error']}"
                ),
            )

        def to_text(result: dict) -> str:
            cubes = result.get("cubes") or []
            parts = [f"Cubos Saiku públicos del SRI ({len(cubes)}):", ""]
            for cube in cubes:
                parts.append(
                    f"- {cube.get('cube')} — cube_id: "
                    f"{cube.get('cube_id') or 'incompleto'}"
                )
            parts.extend(["", f"Fuente: {result['source']}"])
            return "\n".join(parts)

        return render_output(data, format, text_builder=to_text)

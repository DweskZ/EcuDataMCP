from mcp.server.fastmcp import FastMCP

from helpers import sgr_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_sat_tsunami_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_sat_tsunami(limit: int = 30, format: str = "text") -> str:
        """
        List tsunami early-warning SAT stations published by SGR (Gestión de Riesgos).

        Returns station codes and coordinates from the public SAT MapServer.

        Args:
            limit: Max stations to include in the response (default 30)
            format: text | json
        """
        try:
            result = await sgr_client.list_sat_stations(limit=limit)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al listar estaciones SAT: {d['error']}",
            )

        def to_text(data: dict) -> str:
            stations = data.get("stations") or []
            parts = [
                "Estaciones SAT tsunami (SGR)",
                (
                    f"Total en servicio: {data.get('total', len(stations))} "
                    f"(mostrando {len(stations)})"
                ),
                "",
            ]
            for i, st in enumerate(stations, 1):
                parts.append(
                    f"{i}. {st.get('name', '?')} — lon={st.get('lon')}, lat={st.get('lat')}"
                )
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

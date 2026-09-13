from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import sgr_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_list_sat_tsunami_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Listar estaciones del SAT de tsunami", annotations=READ_ONLY)
    @log_tool
    async def list_sat_tsunami(
        limit: int = 30, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
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
            raise ToolError(f"Error al listar estaciones SAT: {e}") from e

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

        return render_structured(result, format, text_builder=to_text)

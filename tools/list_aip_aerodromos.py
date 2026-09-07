from mcp.server.mcpserver import MCPServer

from helpers import aviacion_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_aip_aerodromos_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def list_aip_aerodromos(format: str = "text") -> str:
        """
        List the ICAO designators and names of every aerodrome/helipad with
        a published AIP AD 2.x page, from DGAC's public eAIP
        (ais.aviacioncivil.gob.ec/ifis3) — no login required.

        Use get_aip_aerodromo with one of these designators to fetch that
        aerodrome's full published data sheet (coordinates, runway,
        operating hours, fees, ATS frequencies, etc.).

        Args:
            format: text | json
        """
        result = await aviacion_client.list_aip_aerodromos()

        def to_text(data: dict) -> str:
            aerodromos = data.get("aerodromos") or []
            parts = [f"AIP Ecuador — {data['total']} aeródromo(s) publicado(s):", ""]
            for a in aerodromos:
                parts.append(f"- {a['designador']}: {a['nombre']}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

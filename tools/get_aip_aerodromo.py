from mcp.server.mcpserver import MCPServer

from helpers import aviacion_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_aip_aerodromo_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def get_aip_aerodromo(designador: str, format: str = "text") -> str:
        """
        Fetch the published AIP AD 2.x data sheet for an Ecuadorian
        aerodrome or helipad, from DGAC's public eAIP
        (ais.aviacioncivil.gob.ec/ifis3) — no login required.

        Returns every numbered field the AIP publishes for that aerodrome,
        grouped by ICAO Annex 15 subsection: AD 2.1 location indicator/name,
        AD 2.2 geographic/administrative data (ARP coordinates, elevation,
        magnetic variation, operator contacts), AD 2.3 operating hours, and
        onward through handling/passenger/rescue-and-firefighting services,
        obstacle removal, apron/taxiway data, surface movement guidance,
        obstacles, meteorological info supplied, runway physical
        characteristics, declared distances, lighting, radio navigation
        aids, local traffic regulations, noise abatement, flight
        procedures, and supplementary information. Use list_aip_aerodromos
        to see which designators are published.

        Args:
            designador: ICAO code of the aerodrome/helipad, e.g. SEQM
                (Quito — Mariscal Sucre), SEGU (Guayaquil — José Joaquín de
                Olmedo), SECU (Cuenca — Mariscal Lamar).
            format: text | json
        """
        icao = designador.strip().upper()
        try:
            result = await aviacion_client.get_aip_aerodromo(icao)
        except Exception as e:
            return render_output(
                {"error": str(e), "designador": icao},
                format,
                text_builder=lambda d: (
                    f"Error al consultar AIP de {d['designador']}: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            nombre = f" — {data['nombre']}" if data.get("nombre") else ""
            parts = [f"AIP AD 2 — {data['designador']}{nombre}", ""]
            for s in data.get("secciones") or []:
                parts.append(s["titulo"])
                for c in s.get("campos") or []:
                    if c["valor"]:
                        parts.append(f"   {c['etiqueta']}: {c['valor']}")
                parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

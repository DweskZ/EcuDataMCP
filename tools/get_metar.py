from mcp.server.fastmcp import FastMCP

from helpers import aviacion_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_metar_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_metar(designador: str, format: str = "text") -> str:
        """
        Fetch the most recent METAR/SPECI aerodrome weather reports for an
        Ecuadorian aerodrome or helipad, from DGAC's IFIS site
        (ais.aviacioncivil.gob.ec) — the country's real aeronautical
        information service, publicly queryable with no login.

        Returns each report's type (METAR or SPECI), its UTC observation
        timestamp, and the raw ICAO-format codification text (e.g. "SEQM
        030100Z 30004KT 9999 FEW030 17/08 Q1026 NOSIG RMK A3032=") — decode
        it yourself if you need the plain-language breakdown. Reports are
        usually hourly with occasional SPECI in between; an unknown
        designador returns an empty result rather than an error.

        Args:
            designador: ICAO code of the aerodrome/helipad, e.g. SEQM
                (Quito — Mariscal Sucre), SEGU (Guayaquil — José Joaquín de
                Olmedo), SECU (Cuenca — Mariscal Lamar).
            format: text | json
        """
        icao = designador.strip().upper()
        try:
            result = await aviacion_client.get_metar(icao)
        except Exception as e:
            return render_output(
                {"error": str(e), "designador": icao},
                format,
                text_builder=lambda d: (
                    f"Error al consultar METAR de {d['designador']}: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            reportes = data.get("reportes") or []
            parts = [f"METAR/SPECI — {data['designador']} ({data['total']} reporte(s))", ""]
            if not reportes:
                parts.append("Sin registros de METAR para ese designador.")
                return "\n".join(parts)
            for r in reportes:
                parts.append(f"{r['tipo']} del {r['fecha_utc']} UTC")
                parts.append(f"   {r['raw']}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

from mcp.server.fastmcp import FastMCP

from helpers import aviacion_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_sigmet_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_sigmet(format: str = "text") -> str:
        """
        Fetch currently active SIGMETs (significant meteorological
        information — volcanic ash, severe turbulence/icing, thunderstorms,
        etc.) for Ecuador's FIR, from DGAC's IFIS site
        (ais.aviacioncivil.gob.ec) — publicly queryable with no login.

        Ecuador has a single FIR (SEFG), so this covers the whole country;
        there is no per-aerodrome parameter. Each SIGMET includes the raw
        ICAO-format codification text and the site's own decoded field
        table (Tipo, País, FIR Origen, Número, Desde/Hasta, MWO, FIR
        Afectado, Causa, Fenómeno, Observación, Coordenadas, Posición
        Pronosticada, etc.). Zero results means no advisories are currently
        active, not an error.

        Args:
            format: text | json
        """
        try:
            result = await aviacion_client.get_sigmet()
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al consultar SIGMET: {d['error']}",
            )

        def to_text(data: dict) -> str:
            sigmets = data.get("sigmets") or []
            parts = [f"SIGMET activos — FIR Ecuador (SEFG) — {data['total']} aviso(s)", ""]
            if not sigmets:
                parts.append("Sin SIGMET activos.")
                return "\n".join(parts)
            for s in sigmets:
                parts.append(s["raw"])
                for campo, valor in (s.get("campos") or {}).items():
                    if valor:
                        parts.append(f"   {campo}: {valor}")
                parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

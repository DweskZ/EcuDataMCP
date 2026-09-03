from mcp.server.fastmcp import FastMCP

from helpers import aviacion_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_notam_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_notam(designador: str, format: str = "text") -> str:
        """
        Fetch active NOTAMs (Notices to Airmen) for an Ecuadorian aerodrome
        or helipad, from DGAC's IFIS site (ais.aviacioncivil.gob.ec) —
        publicly queryable with no login.

        Each NOTAM includes its series number (e.g. "A1784/26"), the raw
        ICAO-format text (Q)/A)/B)/C)/D)/E)/F)/G) lines, e.g. runway/navaid
        outages, temporary restrictions, obstacle warnings), and the site's
        own decoded field table (a label -> value map: Tipo, FIR, Código,
        Tránsito, Objetivo, Alcance, Limites, Coordenadas, Comienzo/Término
        validez, Horario, etc. — present when the site fills them in for
        that NOTAM). An unknown designador returns zero NOTAMs rather than
        an error.

        Args:
            designador: ICAO code of the aerodrome/helipad, e.g. SEQM
                (Quito — Mariscal Sucre), SEGU (Guayaquil — José Joaquín de
                Olmedo), SECU (Cuenca — Mariscal Lamar).
            format: text | json
        """
        icao = designador.strip().upper()
        try:
            result = await aviacion_client.get_notam(icao)
        except Exception as e:
            return render_output(
                {"error": str(e), "designador": icao},
                format,
                text_builder=lambda d: (
                    f"Error al consultar NOTAM de {d['designador']}: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            notams = data.get("notams") or []
            nombre = f" — {data['aerodromo_nombre']}" if data.get("aerodromo_nombre") else ""
            parts = [
                f"NOTAM — {data['designador']}{nombre} ({data['total']} activo(s))",
                "",
            ]
            if not notams:
                parts.append("Sin NOTAM activos para ese designador.")
                return "\n".join(parts)
            for n in notams:
                parts.append(f"{n.get('serie') or '(sin serie)'}")
                parts.append(f"   {n['raw']}")
                for campo, valor in (n.get("campos") or {}).items():
                    if valor:
                        parts.append(f"   {campo}: {valor}")
                parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

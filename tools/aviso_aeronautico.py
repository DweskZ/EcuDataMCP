"""Aeronautical notices from DGAC's IFIS (ais.aviacioncivil.gob.ec).

METAR/SPECI weather, NOTAM and SIGMET were three tools over one site with
the same raw-text-plus-fields shape; `tipo` now picks the notice.
"""

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import aviacion_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def _text_metar(data: dict) -> str:
    reportes = data.get("reportes") or []
    parts = [f"METAR/SPECI — {data['designador']} ({data['total']} reporte(s))", ""]
    if not reportes:
        parts.append("Sin registros de METAR para ese designador.")
        return "\n".join(parts)
    for r in reportes:
        parts.append(f"{r['tipo']} del {r['fecha_utc']} UTC")
        parts.append(f"   {r['raw']}")
    parts += ["", f"Fuente: {data.get('url_fuente')}"]
    return "\n".join(parts)


def _text_notam(data: dict) -> str:
    notams = data.get("notams") or []
    nombre = f" — {data['aerodromo_nombre']}" if data.get("aerodromo_nombre") else ""
    parts = [f"NOTAM — {data['designador']}{nombre} ({data['total']} activo(s))", ""]
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


def _text_sigmet(data: dict) -> str:
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


def register_aviso_aeronautico_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Consultar METAR, NOTAM o SIGMET de Ecuador",
        description=(
            "Live aeronautical notices from DGAC/AIS: metar (latest weather "
            "reports) or notam (active notices) for an aerodrome ICAO code, e.g. "
            "SEQM; sigmet (active SIGMETs for the whole FIR, no code needed). "
            "Raw ICAO text."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_aviso_aeronautico(
        tipo: Literal["metar", "notam", "sigmet"],
        designador: str = "",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Fetch aeronautical notices from DGAC's IFIS site
        (ais.aviacioncivil.gob.ec), publicly queryable with no login.

        - metar: most recent METAR/SPECI reports of an aerodrome or helipad
          (type, UTC time, raw ICAO text; usually hourly). Decode the raw
          text yourself for a plain-language breakdown.
        - notam: active NOTAMs of an aerodrome: series number (e.g.
          "A1784/26"), raw Q)/A)/B)/C)/D)/E) text and DGAC's decoded fields.
          For its fixed data sheet use get_aip_aerodromo.
        - sigmet: active SIGMETs (volcanic ash, turbulence, icing, storms)
          for Ecuador's single FIR (SEFG); no per-aerodrome filter. Zero
          results means none are active, not an error.

        An unknown designador returns an empty result rather than an error.

        Args:
            tipo: metar, notam or sigmet.
            designador: ICAO code of the aerodrome, e.g. SEQM (Quito), SEGU
                (Guayaquil), SECU (Cuenca). Required for metar and notam;
                ignored by sigmet.
            format: text | json
        """
        icao = designador.strip().upper()
        if tipo != "sigmet" and not icao:
            raise ToolError(f"`designador` (código ICAO, p. ej. SEQM) es obligatorio para {tipo}.")
        try:
            if tipo == "metar":
                result, text = await aviacion_client.get_metar(icao), _text_metar
            elif tipo == "notam":
                result, text = await aviacion_client.get_notam(icao), _text_notam
            else:
                result, text = await aviacion_client.get_sigmet(), _text_sigmet
        except Exception as e:
            where = f" de {icao}" if icao and tipo != "sigmet" else ""
            raise ToolError(f"Error al consultar {tipo.upper()}{where}: {e}") from e
        return render_structured({"tipo": tipo, **result}, format, text_builder=text)

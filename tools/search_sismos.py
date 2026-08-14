from mcp.server.fastmcp import FastMCP

from helpers import igepn_client
from helpers.format_out import render_output
from helpers.logging import log_tool

_ESTADOS = {
    "confirmed": "revisado por analista",
    "automatic": "solución automática (preliminar)",
    "preliminary": "preliminar",
}


def register_search_sismos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_sismos(
        query: str = "",
        magnitud_minima: float = 0.0,
        dias: int = 0,
        limit: int = 15,
        format: str = "text",
    ) -> str:
        """
        Search recent earthquakes in Ecuador from the Instituto Geofísico (IG-EPN).

        Returns the IG-EPN seismic catalog feed: magnitude, depth, coordinates,
        local/UTC time, review status and nearest-place description, with a link
        to each event page. Data is cached ~2 minutes.

        Args:
            query: Free text over location/id (e.g. "Quito", "Esmeraldas")
            magnitud_minima: Minimum magnitude (e.g. 4.0)
            dias: Only events from the last N days (0 = all available)
            limit: Max events to return (default 15, max 100)
            format: text | json
        """
        try:
            result = await igepn_client.list_earthquakes(
                query=query,
                min_magnitud=magnitud_minima,
                dias=dias,
                limit=limit,
            )
        except Exception as e:
            err = {"error": str(e), "source": "IG-EPN"}
            return render_output(
                err,
                format,
                text_builder=lambda d: f"Error al consultar sismos IG-EPN: {d['error']}",
            )

        def to_text(data: dict) -> str:
            events = data.get("events") or []
            if not events:
                return (
                    "No se encontraron sismos con esos filtros. "
                    "Prueba bajar magnitud_minima o ampliar dias."
                )
            parts = [
                "Sismos recientes en Ecuador (Instituto Geofísico - EPN)",
                (
                    f"Total coincidencias: {data.get('total', len(events))} "
                    f"(mostrando {len(events)})"
                ),
                "",
            ]
            for i, ev in enumerate(events, 1):
                estado = _ESTADOS.get(ev.get("estado", ""), ev.get("estado", "?"))
                parts.append(
                    f"{i}. M {ev.get('magnitud')} — {ev.get('localizacion', '?')}"
                )
                parts.append(
                    f"   Hora local: {ev.get('tiempo_local')} (UTC: {ev.get('tiempo_utc')})"
                )
                parts.append(
                    f"   Profundidad: {ev.get('profundidad_km')} km — "
                    f"lat={ev.get('latitud')}, lon={ev.get('longitud')} — "
                    f"estado: {estado}"
                )
                if ev.get("url"):
                    parts.append(f"   Detalle: {ev['url']}")
                parts.append("")
            parts.append(
                "Fuente: IG-EPN (www.igepn.edu.ec). Información pública de apoyo; "
                "no sustituye los canales oficiales de alerta."
            )
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

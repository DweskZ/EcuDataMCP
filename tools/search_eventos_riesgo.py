from mcp.server.fastmcp import FastMCP

from helpers import sgr_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_eventos_riesgo_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_eventos_riesgo(
        query: str = "",
        provincia: str = "",
        canton: str = "",
        evento: str = "",
        estado: str = "",
        limit: int = 15,
        format: str = "text",
    ) -> str:
        """
        Search emergency/risk events from Ecuador's SGR COE (Gestión de Riesgos).

        Returns recent recorded events such as landslides, floods, structural damage,
        with province/canton, status (Seguimiento/Cierre), impacts and description.
        Data comes from the public ArcGIS COE2 service (cached ~5 minutes).

        Args:
            query: Free text (sector, cause, description keywords)
            provincia: Province filter (e.g. "Pichincha")
            canton: Canton filter (e.g. "Quito")
            evento: Event type filter (e.g. "Deslizamiento", "Inundación", "Aluvión")
            estado: Status filter (e.g. "Seguimiento", "Cierre")
            limit: Max events to return (default 15, max 100)
            format: text | json
        """
        try:
            result = await sgr_client.list_risk_events(
                query=query,
                provincia=provincia,
                canton=canton,
                evento=evento,
                estado=estado,
                limit=limit,
            )
        except Exception as e:
            err = {"error": str(e), "source": "SGR COE2"}
            return render_output(
                err,
                format,
                text_builder=lambda d: f"Error al consultar eventos SGR: {d['error']}",
            )

        def to_text(data: dict) -> str:
            events = data.get("events") or []
            if not events:
                return (
                    "No se encontraron eventos de riesgo con esos filtros. "
                    "Prueba provincia='Guayas', evento='Inundación', estado='Seguimiento'."
                )
            parts = [
                "Eventos de riesgo / emergencia (SGR COE)",
                (
                    f"Total coincidencias: {data.get('total', len(events))} "
                    f"(mostrando {len(events)})"
                ),
                f"Fuente: {data.get('source')}",
                "",
            ]
            for i, ev in enumerate(events, 1):
                parts.append(
                    f"{i}. {ev.get('Evento', 'Evento')} — {ev.get('EstadoDelEvento', '?')}"
                )
                parts.append(
                    f"   Lugar: {ev.get('Provincia', '?')} / {ev.get('Canton', '?')} / "
                    f"{ev.get('Parroquia', '')}"
                )
                if ev.get("Sector"):
                    parts.append(f"   Sector: {ev['Sector']}")
                if ev.get("FechaDelEvento"):
                    parts.append(
                        f"   Fecha: {ev.get('FechaDelEvento')} {ev.get('HoraDelEvento', '')}".strip()
                    )
                if ev.get("NivelDelEvento"):
                    parts.append(f"   Nivel: {ev['NivelDelEvento']}")
                impacts = []
                for label, key in (
                    ("fallecidos", "PersonasFallecidas"),
                    ("heridos", "PersonasHeridas"),
                    ("familias afectadas", "FamiliasAfectadas"),
                    ("viviendas afectadas", "ViviendasAfectadas"),
                ):
                    val = ev.get(key) or 0
                    try:
                        if float(val) > 0:
                            impacts.append(f"{label}={val}")
                    except (TypeError, ValueError):
                        pass
                if impacts:
                    parts.append(f"   Impacto: {', '.join(impacts)}")
                desc = (ev.get("DescripcionGeneralDeEvento") or "").strip()
                if desc:
                    parts.append(f"   Descripción: {desc[:280]}")
                parts.append("")
            parts.append(
                "Tip: filtra con estado='Seguimiento' para eventos activos. "
                "Geo de apoyo: lookup_ubicacion(nivel='canton')."
            )
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

from mcp.server.fastmcp import FastMCP

from helpers import sgr_publicaciones_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_sgr_sitreps_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_sgr_sitreps(query: str = "", format: str = "text") -> str:
        """
        List SGR's SITREP ("Informes de Situación") archive of adverse-event
        dossiers (gestionderiesgos.gob.ec), 2016-2026.

        This is a DIFFERENT source from search_eventos_riesgo, which reads
        SGR's live ArcGIS COE2 snapshot (current/in-progress events only,
        no history). This tool instead lists ~54 multi-year dossiers —
        earthquakes, forest-fire seasons, rainy seasons, landslides,
        volcanic activity — each a real event with a status (EN CURSO /
        CERRADO / EN OBSERVACIÓN) and its own page. Follow up with
        get_sgr_sitrep_archivos(url) on one event's "url" to get its
        actual SITREP PDF report links.

        Args:
            query: Free text matched (accent-insensitive) against the
                event's titulo, estado, or descripcion, e.g. "terremoto",
                "en curso", "manabi". Empty returns all events.
            format: text | json
        """
        try:
            result = await sgr_publicaciones_client.list_eventos_sitrep(query=query)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar el archivo SITREP de SGR: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            eventos = data.get("eventos") or []
            parts = [
                (
                    f"SGR — Informes de Situación (SITREP) — {data['total']} resultado(s) "
                    f"de {data['total_en_pagina']} eventos (2016-2026)"
                ),
                "",
            ]
            if not eventos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, e in enumerate(eventos, 1):
                parts.append(f"{i}. {e.get('titulo')} [{e.get('estado')}]")
                parts.append(f"   Fecha: {e.get('fecha_texto')}")
                if e.get("descripcion"):
                    parts.append(f"   {e['descripcion']}")
                parts.append(f"   {e.get('url')}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

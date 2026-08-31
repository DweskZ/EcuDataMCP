from mcp.server.fastmcp import FastMCP

from helpers import igepn_informes_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_informes_igepn_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_informes_igepn(
        query: str = "",
        grupo: str = "",
        anio: int = 0,
        limit: int = 15,
        format: str = "text",
    ) -> str:
        """
        Search the IG-EPN PDF report archive (Instituto Geofísico):
        daily/weekly/monthly/special seismic bulletins, volcanic "IG Al
        Instante" alerts, field/annual reports, etc. Different from
        search_sismos, which reads the raw earthquake catalog feed -- this
        searches the narrative/PDF report archive instead. Use
        get_informe_igepn afterwards to download and read one report's text.

        Args:
            query: Free text over report name/volcano (e.g. "cotopaxi", "trimestral")
            grupo: "sismico" | "volcanico" | "" (both)
            anio: Report year (0 = current year)
            limit: Max reports to return (default 15, max 30)
            format: text | json
        """
        try:
            result = await igepn_informes_client.search_informes(
                query=query, grupo=grupo, anio=anio, limit=limit
            )
        except Exception as e:
            err = {"error": str(e), "source": "IG-EPN Búsqueda de Informes"}
            return render_output(
                err,
                format,
                text_builder=lambda d: f"Error al buscar informes IG-EPN: {d['error']}",
            )

        def to_text(data: dict) -> str:
            informes = data.get("informes") or []
            parts = [
                f"Informes IG-EPN — grupo: {data['grupo']}, año: {data['anio']}",
                f"Coincidencias: {data['coincidencias']} de {data['total_en_pagina']} en la página consultada",
                "",
            ]
            if not informes:
                parts.append("Sin coincidencias. Prueba otro año o amplía la búsqueda.")
            for i, inf in enumerate(informes, 1):
                parts.append(f"{i}. {inf['nombre']}" + (f" — {inf['volcan']}" if inf.get("volcan") else ""))
                parts.append(
                    f"   Versión: {inf.get('version', '?')} — Publicado: {inf.get('fecha_publicacion', '?')}"
                )
            parts.append("")
            parts.append(data["nota"])
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

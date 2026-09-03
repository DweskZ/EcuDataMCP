from mcp.server.fastmcp import FastMCP

from helpers import arcotel_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_arcotel_boletines_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_arcotel_boletines(query: str = "", format: str = "text") -> str:
        """
        List ARCOTEL's (Agencia de Regulación y Control de las
        Telecomunicaciones) "Boletín Estadístico del Sector de las
        Telecomunicaciones" PDFs — annual/topical statistical bulletins
        published on the institutional site (www.arcotel.gob.ec), outside
        CKAN.

        Confirmed live range: 2015 through 2024 (no 2025/2026 bulletin
        published yet as of this check). Lower-frequency and more
        topic-driven than search_arcotel_reportes_mensuales (one-per-month
        series, 2017-2026) -- entries here are things like "Servicio
        Portador — Agosto" or "Roaming-Nacional Automático", not a
        uniform monthly cadence. Also separate from ARCOTEL's
        frozen-since-2021/2022 CKAN organization. PDF only — no
        CSV/XLSX/API. Returns direct URLs, not parsed table data —
        download them yourself, via download_resource, or via read_pdf.

        Args:
            query: Free text matched against the entry's label, year, or
                URL (accent-insensitive), e.g. "roaming", "2020",
                "portabilidad". Empty returns all entries.
            format: text | json
        """
        try:
            result = await arcotel_client.search_boletines_estadisticos(query=query)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    "Error al consultar los Boletines Estadísticos de ARCOTEL: "
                    f"{d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"ARCOTEL — Boletín Estadístico — {data['total']} resultado(s) "
                    f"de {data['total_en_pagina']} entradas"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, f in enumerate(archivos, 1):
                anio = f.get("anio")
                prefix = f"[{anio}] " if anio else ""
                parts.append(f"{i}. {prefix}{f.get('label')} [{f.get('format')}]")
                parts.append(f"   {f.get('url')}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

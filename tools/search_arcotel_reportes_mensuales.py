from mcp.server.fastmcp import FastMCP

from helpers import arcotel_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_arcotel_reportes_mensuales_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_arcotel_reportes_mensuales(query: str = "", format: str = "text") -> str:
        """
        List ARCOTEL's (Agencia de Regulación y Control de las
        Telecomunicaciones) "Reportes Estadísticos Mensuales" PDFs — the
        regulator's monthly telecom-sector statistics series, published on
        the institutional site (www.arcotel.gob.ec), outside CKAN.

        Confirmed live range: January 2017 through June 2026 (most recent
        upload lags today by roughly 2 months). 2023-2026 is one PDF per
        month; 2017-2022 mixes months with ad hoc topical infographics.
        This is a separate, higher-frequency series from
        search_arcotel_boletines (annual/topical bulletins, 2015-2024) and
        from ARCOTEL's frozen-since-2021/2022 CKAN organization. PDF only —
        no CSV/XLSX/API. Returns direct URLs, not parsed table data —
        download them yourself, via download_resource, or via read_pdf.

        Args:
            query: Free text matched against the entry's label, year, or
                URL (accent-insensitive), e.g. "junio 2026", "2025",
                "internet". Empty returns all entries.
            format: text | json
        """
        try:
            result = await arcotel_client.search_reportes_mensuales(query=query)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    "Error al consultar los Reportes Estadísticos Mensuales de "
                    f"ARCOTEL: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"ARCOTEL — Reportes Estadísticos Mensuales — {data['total']} "
                    f"resultado(s) de {data['total_en_pagina']} entradas"
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

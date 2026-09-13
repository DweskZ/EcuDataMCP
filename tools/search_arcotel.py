from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import arcotel_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_search_arcotel_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Buscar boletines y reportes estadísticos de ARCOTEL", annotations=READ_ONLY)
    @log_tool
    async def search_arcotel(
        tipo: Literal["boletines", "reportes_mensuales"],
        query: str = "",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        List ARCOTEL's (Agencia de Regulación y Control de las
        Telecomunicaciones) statistical PDF series, published on the
        institutional site (www.arcotel.gob.ec), outside CKAN. Both series
        are separate from ARCOTEL's frozen-since-2021/2022 CKAN
        organization. PDF only — no CSV/XLSX/API. Returns direct URLs, not
        parsed table data — download them yourself, via download_resource,
        or via read_pdf.

        Args:
            tipo: "boletines" for the "Boletín Estadístico del Sector de
                las Telecomunicaciones" (annual/topical, confirmed live
                2015-2024, entries like "Servicio Portador — Agosto" or
                "Roaming-Nacional Automático", not a uniform monthly
                cadence), or "reportes_mensuales" for the "Reportes
                Estadísticos Mensuales" (higher-frequency, confirmed live
                January 2017 through June 2026, one PDF per month since
                2023, mixed with ad hoc topical infographics 2017-2022).
            query: Free text matched against the entry's label, year, or
                URL (accent-insensitive), e.g. "roaming", "2020",
                "portabilidad" for boletines, or "junio 2026", "2025",
                "internet" for reportes_mensuales. Empty returns all
                entries.
            format: text | json
        """
        if tipo == "reportes_mensuales":
            fetch = arcotel_client.search_reportes_mensuales
        elif tipo == "boletines":
            fetch = arcotel_client.search_boletines_estadisticos
        else:
            raise ToolError(
                f"tipo inválido: {tipo!r} (usa 'boletines' o 'reportes_mensuales')"
            )

        try:
            result = await fetch(query=query)
        except Exception as e:
            raise ToolError(f"Error al consultar ARCOTEL ({tipo}): {e}") from e

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"{data.get('source')} — {data['total']} resultado(s) "
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

        return render_structured(result, format, text_builder=to_text)

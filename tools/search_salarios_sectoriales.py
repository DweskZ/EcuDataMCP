from mcp.server.fastmcp import FastMCP

from helpers import salarios_sectoriales_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_salarios_sectoriales_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_salarios_sectoriales(
        anio: int | None = None, format: str = "text"
    ) -> str:
        """
        List Ecuador's sectoral minimum wage table documents (salarios
        mínimos sectoriales — wage floors per branch of economic activity,
        set by the Consejo Nacional de Trabajo y Salarios, distinct from the
        single national Salario Básico Unificado).

        Scraped from the Ministerio del Trabajo's document library
        (trabajo.gob.ec/biblioteca/), which — unlike the ministry's dynamic
        pages — actually responds and lists the whole legal library with
        stable per-document download links. Confirmed coverage: one entry
        per year for 2020-2025 (most years have both a spreadsheet and a PDF
        of the signed annex). No 2026 table has been published — the 2025
        table remains in force by inaction; see the returned "nota" field.
        Some entries are the underlying Acuerdo Ministerial rather than the
        table itself, titled by the year it was *signed* (often the year
        before the table it sets applies to) — if a specific year looks
        thin, also check the year before it.

        Returns document metadata and a "Ver" link per entry, not file
        contents — the link redirects to the real PDF/XLS/XLSX; download it
        via download_resource or preview it via preview_resource_data.

        Args:
            anio: Filter to this year (as printed in the document's own
                title). None returns every year found.
            format: text | json
        """
        try:
            result = await salarios_sectoriales_client.search_tablas_sectoriales(
                anio=anio
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "anio": anio},
                format,
                text_builder=lambda d: (
                    f"Error al consultar salarios sectoriales del Ministerio "
                    f"del Trabajo: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            tablas = data.get("tablas") or []
            parts = [
                (
                    f"Salarios Mínimos Sectoriales (Ministerio del Trabajo) — "
                    f"{data['total']} resultado(s) de {data['total_en_biblioteca']} "
                    f"en la biblioteca"
                ),
                "",
            ]
            if not tablas:
                parts.append("Sin resultados.")
            else:
                for i, t in enumerate(tablas, 1):
                    parts.append(f"{i}. [{t.get('anio')}] {t.get('titulo')}")
                    parts.append(f"   {t.get('url_ver')}")
            parts.append("")
            parts.append(f"Nota: {data.get('nota')}")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

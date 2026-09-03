from mcp.server.fastmcp import FastMCP

from helpers import trabajo_boletin_anual_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_trabajo_boletin_anual_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_trabajo_boletin_anual(query: str = "", format: str = "text") -> str:
        """
        List known editions of Ministerio del Trabajo's "Boletín Estadístico
        Anual: El Mercado Laboral en el Ecuador" — an annual PDF report on
        the Ecuadorian labor market, sourced from INEC's ENEMDU survey plus
        the ministry's own administrative registries (a derived analysis,
        not a primary survey of its own).

        IMPORTANT — this is NOT a complete historical series: only 3
        editions are known (2020, 2021, 2022). The only page that ever
        listed multiple editions cannot be scraped live (it violates
        HTTP/1.1 with duplicated Transfer-Encoding headers, confirmed
        reproducible, not a timeout as prior notes assumed) and today only
        links the 2022 edition even when fetched by hand — 2020 and 2021
        were recovered from a January 2024 Wayback Machine snapshot of that
        same page and re-verified live. No 2023-2025 edition was found
        despite checking the site's search API and a handful of plausible
        filename guesses. Returns direct PDF URLs, not file contents —
        download them yourself or via download_resource / read_pdf.

        Args:
            query: Free text matched (accent-insensitive) against the
                edition's year, title, or URL, e.g. "2021". Empty returns
                all known editions.
            format: text | json
        """
        try:
            result = await trabajo_boletin_anual_client.search_boletines(query=query)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    "Error al consultar el Boletín Estadístico Anual del "
                    f"Ministerio del Trabajo: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            ediciones = data.get("ediciones") or []
            parts = [
                (
                    f"Boletín Estadístico Anual — Mercado Laboral (MDT) — "
                    f"{data['total']} resultado(s) de {data['total_conocido']} "
                    "ediciones conocidas"
                ),
                "",
                "ADVERTENCIA: archivo incompleto, no es la serie histórica "
                "completa. " + data.get("nota_cobertura", ""),
                "",
            ]
            if not ediciones:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, e in enumerate(ediciones, 1):
                parts.append(f"{i}. {e.get('titulo')} [{e.get('formato')}]")
                parts.append(f"   {e.get('url')}")
            parts.append("")
            parts.append(f"Página índice (parcialmente vigente): {data.get('url_indice')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

from mcp.server.fastmcp import FastMCP

from helpers import censo_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_censo_recursos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_censo_recursos(
        query: str = "",
        limit: int = 30,
        offset: int = 0,
        format: str = "text",
    ) -> str:
        """
        Search INEC's dedicated Census 2022 microsite (censoecuador.gob.ec)
        for direct microdata/methodology file links.

        Far more complete than the general "Censo de Población y Vivienda"
        result from search_inec_estadisticas: full microdata at sector,
        cantón, and city-block ("manzana"/MANLOC) level in CSV, SPSS (SAV),
        and REDATAM formats, plus the 2010 and 2001 censuses recoded onto
        2022 geography for comparability, variable dictionaries, and
        methodology/quality documents. Returns metadata and direct URLs
        only, never file contents -- these are large microdata archives
        (multi-hundred-MB in some cases), not previewable through this tool.

        Args:
            query: Free text matched (accent-insensitive) against the file
                label, e.g. "manlo" (city-block level), "sector", "2010",
                "spss", "diccionario", "metodologia". Empty returns every
                file found.
            limit: Max results (default 30, max 100).
            offset: Pagination offset over the matched set.
            format: text | json
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        try:
            result = await censo_client.search_censo_recursos(
                query=query, limit=limit, offset=offset
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al buscar recursos del Censo Ecuador: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            recursos = data.get("recursos") or []
            parts = [
                (
                    f"Censo Ecuador 2022 — {data['total']} resultado(s) de "
                    f"{data['total_recursos']} archivos (mostrando {len(recursos)}, "
                    f"offset={data['offset']})"
                ),
                "",
            ]
            if not recursos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, r in enumerate(recursos, 1):
                parts.append(f"{i}. {r.get('label')} [{r.get('format')}]")
                parts.append(f"   {r.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

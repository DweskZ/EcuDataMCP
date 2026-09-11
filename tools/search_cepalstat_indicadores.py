from mcp.server.mcpserver import MCPServer

from helpers import cepalstat_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_cepalstat_indicadores_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def search_cepalstat_indicadores(
        query: str = "", lang: str = "es", format: str = "text"
    ) -> str:
        """
        Search CEPALSTAT (CEPAL/ECLAC's public statistics API,
        api-cepalstat.cepal.org) for an indicator by name — 2,059
        indicators across Demográficos y sociales, Económicos,
        Ambientales, and Temas transversales (incluye los ODS).

        NOT an Ecuador-only source: CEPALSTAT is CEPAL's regional catalog
        for all of Latin America and the Caribbean. Use this to find the
        indicator_id, then get_cepalstat_indicador to fetch Ecuador's
        observations specifically.

        Typical workflow: search_cepalstat_indicadores → get_cepalstat_indicador

        Args:
            query: Free text matched (accent-insensitive) against the
                indicator's name or its thematic-area breadcrumb, e.g.
                "poblacion", "pobreza", "comercio exterior". Empty returns
                the full catalog (large — prefer a query).
            lang: "es" (default) or "en"
            format: text | json
        """
        try:
            result = await cepalstat_client.search_indicadores(query=query, lang=lang)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: f"Error al buscar indicadores en CEPALSTAT: {d['error']}",
            )

        def to_text(data: dict) -> str:
            indicadores = data.get("indicadores") or []
            parts = [
                (
                    f"CEPALSTAT — {data['total']} indicador(es) de {data['total_catalogo']} "
                    "en el catálogo"
                ),
                "",
            ]
            if not indicadores:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, ind in enumerate(indicadores[:50], 1):
                parts.append(f"{i}. {ind['nombre']} (indicator_id={ind['indicator_id']})")
                parts.append(f"   Área: {ind['area']}")
            if len(indicadores) > 50:
                parts.append(f"... y {len(indicadores) - 50} más (usa format=json para verlos todos)")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

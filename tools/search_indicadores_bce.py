import logging

from mcp.server.fastmcp import FastMCP

from helpers import bce_client
from helpers.format_out import render_output
from helpers.logging import MAIN_LOGGER_NAME, log_tool

logger = logging.getLogger(MAIN_LOGGER_NAME)


def register_search_indicadores_bce_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_indicadores_bce(
        query: str = "",
        limit: int = 20,
        offset: int = 0,
        format: str = "text",
    ) -> str:
        """
        Search the Banco Central del Ecuador (BCE) statistical catalog.

        Covers monetary/financial statistics, public finances, external
        sector (foreign trade), and real sector (GDP, employment/
        unemployment, consumer confidence, oil production, cement
        production, and more) — each result is an indicator group
        (id_grupo) whose time series data you fetch with get_indicador_bce.
        Some groups hold a single series, others dozens under a broader
        title (e.g. "desempleo" is a series inside the "mercado laboral"
        group, not a group of its own — matched here too, not just group
        titles). Does NOT cover Ecuador's own inflation (CPI) or poverty
        statistics — those are INEC's domain, try search_anda instead.

        First call after the cache expires (24h) takes ~10-15s: matching
        against series names, not just group titles, means fetching every
        group's metadata (~78 groups) once to build the search index.
        Cached after that.

        Args:
            query: Free text matched against the group's description, its
                section/subsection, and its individual series labels
                (accent-insensitive)
            limit: Max results (default 20, max 100)
            offset: Pagination offset over the matched set
            format: text | json
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        try:
            result = await bce_client.search_indicadores(
                query=query, limit=limit, offset=offset
            )
        except Exception as e:
            logger.exception("search_indicadores_bce failed (query=%r)", query)
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar el catálogo del BCE: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            indicadores = data.get("indicadores") or []
            parts = [
                (
                    f"Catálogo BCE — {data['total']} resultado(s) "
                    f"(mostrando {len(indicadores)}, offset={data['offset']})"
                ),
                "",
            ]
            if not indicadores:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, ind in enumerate(indicadores, 1):
                parts.append(f"{i}. {ind.get('descripcion')}")
                parts.append(f"   id_grupo: {ind.get('id_grupo')}")
                ubicacion = " > ".join(
                    part
                    for part in (ind.get("seccion"), ind.get("subseccion"))
                    if part
                )
                if ubicacion:
                    parts.append(f"   {ubicacion}")
                if ind.get("series_coincidentes"):
                    parts.append(
                        "   Coincide vía serie: "
                        + ", ".join(ind["series_coincidentes"])
                    )
                parts.append("")
            parts.append(
                "Tip: usa get_indicador_bce(id_grupo=...) para la serie de tiempo."
            )
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

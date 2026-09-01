import logging

from mcp.server.fastmcp import FastMCP

from helpers import bce_client, bce_equivalence, bce_iem_client
from helpers.format_out import render_output
from helpers.logging import MAIN_LOGGER_NAME, log_tool

logger = logging.getLogger(MAIN_LOGGER_NAME)


def register_compare_bce_sources_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def compare_bce_sources(
        query: str = "",
        limit: int = 100,
        historico: bool = False,
        format: str = "text",
    ) -> str:
        """Build a cautious BCEData ↔ IEM candidate-equivalence map.

        Matching uses normalized group/series/table labels. It reports
        candidate overlaps and source-only entries, but does not claim that
        two labels have identical definitions. Confirm unit, frequency,
        coverage, values and revisions before combining them.
        """
        limit = min(max(limit, 1), 100)
        try:
            bce_snapshot = await bce_client._fetch_catalog_snapshot()
            iem_catalog = await bce_iem_client.search_tables(
                query=query,
                limit=limit,
                historico=historico,
            )
            result = bce_equivalence.build_equivalence_map(
                bce_snapshot, iem_catalog
            )
            result["bce_consultado_en"] = bce_snapshot.get("consultado_en")
            result["iem_consultado_en"] = iem_catalog.get("catalogado_en")
            return render_output(
                result,
                format,
                text_builder=lambda data: (
                    "Mapa candidato BCEData ↔ IEM\n"
                    f"Coincidencias candidatas: {len(data['equivalencias_candidatas'])}\n"
                    f"Solo IEM por etiquetas: {len(data['iem_solo_por_etiquetas'])}\n"
                    f"Solo BCEData por etiquetas: {len(data['bcedata_solo_por_etiquetas'])}\n\n"
                    + data["nota"]
                ),
            )
        except Exception as exc:
            logger.exception("compare_bce_sources failed (query=%r)", query)
            return render_output(
                {"error": str(exc)},
                format,
                text_builder=lambda data: f"Error: {data['error']}",
            )

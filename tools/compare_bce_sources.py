import logging
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import bce_client, bce_equivalence, bce_equivalence_store, bce_iem_client
from helpers.format_out import render_structured
from helpers.logging import MAIN_LOGGER_NAME, log_tool
from helpers.response_contract import with_response_metadata
from helpers.tool_meta import WRITES_LOCAL_ARTIFACTS

logger = logging.getLogger(MAIN_LOGGER_NAME)


def register_compare_bce_sources_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Comparar BCEData contra IEM (operador)", annotations=WRITES_LOCAL_ARTIFACTS
    )
    @log_tool
    async def compare_bce_sources(
        query: str = "",
        limit: int = 100,
        historico: bool = False,
        guardar_revision: bool = False,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
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
            if guardar_revision:
                result["revision_guardada"] = bce_equivalence_store.persist_review_map(result)
            result = with_response_metadata(
                result,
                source="Banco Central del Ecuador — BCEData e IEM",
                source_url="https://contenido.bce.fin.ec/bcedata/",
                freshness="comparacion_de_catalogos_en_vivo",
                schema_name="bce_equivalencias_candidatas_v1",
                schema_fields=[
                    "equivalencias_candidatas", "iem_solo_por_etiquetas",
                    "bcedata_solo_por_etiquetas", "nota",
                ],
                consulted_at=bce_snapshot.get("consultado_en"),
                published_at=iem_catalog.get("catalogado_en"),
            )
            return render_structured(
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
            raise ToolError(f"Error al comparar BCEData con IEM: {exc}") from exc

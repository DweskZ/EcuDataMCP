import logging
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import supercias_financials
from helpers.format_out import render_structured
from helpers.logging import MAIN_LOGGER_NAME, log_tool
from helpers.tool_meta import READ_ONLY

logger = logging.getLogger(MAIN_LOGGER_NAME)


def register_search_ranking_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Rankear compañías por indicadores financieros", annotations=READ_ONLY
    )
    @log_tool
    async def search_ranking(
        anio: int | None = None,
        ciiu_n1: str = "",
        order_by: str = "posicion_general",
        descending: bool = False,
        limit: int = 20,
        offset: int = 0,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Rank/filter Supercías companies by financial indicators for a fiscal year.

        Filter by year and/or CIIU level-1 economic activity (single letter,
        e.g. "C" for manufacturing), sorted by any indicator column (defaults
        to the dataset's own precomputed posicion_general). Each result
        includes the company's nombre/ruc alongside its financials. Covers
        only the last few cached fiscal years, not the full history. Use
        get_financials for one company's full detail, or get_compania_info
        for legal/registry data (address, legal representative, etc.).

        Args:
            anio: Optional fiscal year filter.
            ciiu_n1: Optional CIIU level-1 filter, e.g. "C", "G", "I".
            order_by: Column to sort by (e.g. "posicion_general", "activos",
                "roe"). Raises an error listing valid columns if unknown.
            descending: Set true for "top N" style queries (e.g. highest
                ingresos_ventas/roe first). posicion_general is already
                rank-ordered ascending (1 = best), so leave this false when
                sorting by it.
            limit: Max results (default 20, max 100).
            offset: Pagination offset.
            format: text | json
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        try:
            result = await supercias_financials.search_ranking(
                anio=anio,
                ciiu_n1=ciiu_n1,
                order_by=order_by,
                descending=descending,
                limit=limit,
                offset=offset,
            )
        except supercias_financials.FinancialsDbUnavailable as e:
            raise ToolError(str(e)) from e
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            logger.exception(
                "search_ranking failed (anio=%r, ciiu_n1=%r)", anio, ciiu_n1
            )
            raise ToolError(f"Error al consultar el ranking de Supercías: {e}") from e

        def to_text(data: dict) -> str:
            companias = data.get("companias") or []
            parts = [
                (
                    f"Ranking Supercías — {data['total']} resultado(s) "
                    f"(mostrando {len(companias)}, offset={data['offset']})"
                ),
                "",
            ]
            if not companias:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, c in enumerate(companias, 1):
                nombre = c.get("nombre") or f"Expediente {c.get('expediente')}"
                parts.append(
                    f"{i}. {nombre} — año {c.get('anio')} "
                    f"— posición {c.get('posicion_general')}"
                )
                if c.get("ruc"):
                    parts.append(f"   RUC: {c['ruc']}  ·  Expediente: {c.get('expediente')}")
                else:
                    parts.append(f"   Expediente: {c.get('expediente')}")
                parts.append(f"   CIIU: {c.get('ciiu_n1')} / {c.get('ciiu_n6')}")
                if c.get("ingresos_ventas") is not None:
                    parts.append(f"   Ingresos por ventas: {c['ingresos_ventas']}")
                if c.get("activos") is not None:
                    parts.append(f"   Activos: {c['activos']}")
                if c.get("roe") is not None:
                    parts.append(f"   ROE: {c['roe']}")
                parts.append("")
            parts.append(
                "Tip: usa get_financials(expediente_or_ruc=...) para el detalle "
                "completo de una compañía."
            )
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

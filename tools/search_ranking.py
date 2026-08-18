import logging

from mcp.server.fastmcp import FastMCP

from helpers import supercias_financials
from helpers.format_out import render_output
from helpers.logging import MAIN_LOGGER_NAME, log_tool

logger = logging.getLogger(MAIN_LOGGER_NAME)


def register_search_ranking_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_ranking(
        anio: int | None = None,
        ciiu_n1: str = "",
        order_by: str = "posicion_general",
        limit: int = 20,
        offset: int = 0,
        format: str = "text",
    ) -> str:
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
            order_by: Column to sort ascending by (e.g. "posicion_general",
                "activos", "roe"). Falls back to posicion_general if unknown.
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
                limit=limit,
                offset=offset,
            )
        except supercias_financials.FinancialsDbUnavailable as e:
            return render_output(
                {"error": str(e), "anio": anio, "ciiu_n1": ciiu_n1 or None},
                format,
                text_builder=lambda d: d["error"],
            )
        except Exception as e:
            logger.exception(
                "search_ranking failed (anio=%r, ciiu_n1=%r)", anio, ciiu_n1
            )
            return render_output(
                {"error": str(e), "anio": anio, "ciiu_n1": ciiu_n1 or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar el ranking de Supercías: {d['error']}"
                ),
            )

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

        return render_output(result, format, text_builder=to_text)

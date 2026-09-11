from mcp.server.mcpserver import MCPServer

from helpers import bce_calendario_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_bce_calendario_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def search_bce_calendario(
        query: str = "",
        categoria: str = "",
        periodicidad: str = "",
        desde: str = "",
        hasta: str = "",
        solo_proximas: bool = False,
        limit: int = 50,
        offset: int = 0,
        format: str = "text",
    ) -> str:
        """
        Search BCE's own statistical publication calendar — scheduled
        release dates for IEM, Cuentas Nacionales, IMAEc, balance of
        payments, and more, each with category, periodicity, reference
        period, and a direct link to the publication's page.

        Distinct from search_bce_publicaciones (a rolling window of ~30
        already-published items, no future dates): this is BCE's own
        forward-looking release schedule for the full calendar year.

        Args:
            query: Free text matched against the publication name or its
                observations note (accent-insensitive). Empty matches all.
            categoria: Exact category filter (accent-insensitive), e.g.
                "cuentas nacionales", "balanza de pagos y comercio exterior".
            periodicidad: Exact periodicity filter, e.g. "Mensual", "Anual",
                "Trimestral", "Semanal".
            desde: Restrict to release date >= this date (YYYY-MM-DD).
            hasta: Restrict to release date <= this date (YYYY-MM-DD).
            solo_proximas: If true, only releases scheduled today or later.
            limit: Max results (1-200, default 50).
            offset: Pagination offset over the matched set.
            format: text | json
        """
        try:
            result = await bce_calendario_client.search_calendario(
                query=query,
                categoria=categoria,
                periodicidad=periodicidad,
                desde=desde,
                hasta=hasta,
                solo_proximas=solo_proximas,
                limit=limit,
                offset=offset,
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar el calendario de publicaciones del BCE: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            publicaciones = data.get("publicaciones") or []
            parts = [
                (
                    f"Calendario de Publicaciones (BCE) — {data['total']} resultado(s) de "
                    f"{data['total_calendario']} entradas"
                ),
                "",
            ]
            if not publicaciones:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for p in publicaciones:
                parts.append(f"{p['fecha']} ({p['dia_semana']}) — {p['nombre']}")
                parts.append(f"   {p['categoria']} | {p['periodicidad']} | {p['tipo']}")
                if p.get("periodo_referencia"):
                    parts.append(f"   Período de referencia: {p['periodo_referencia']}")
                if p.get("observaciones"):
                    parts.append(f"   Nota: {p['observaciones']}")
                parts.append(f"   {p['enlace']}")
                parts.append("")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

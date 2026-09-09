from mcp.server.mcpserver import MCPServer

from helpers import bce_cuentas_nacionales_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_bce_cuentas_nacionales_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def search_bce_cuentas_nacionales(
        query: str = "", format: str = "text"
    ) -> str:
        """
        List BCE Cuentas Nacionales page families — annual, quarterly, and
        regional national accounts packages, the historical retropolation
        series (PIB back to 1965), input-output and social-accounting
        matrices, fixed-base (2007=100) series, the bioeconomy thematic
        satellite account, and IMAEC monthly results.

        Distinct from search_indicadores_bce (BCEData's own PIB aggregates)
        and from get_bce_iem_table (IEM's monthly bulletin tables): this
        covers the actual national-accounts publication packages — Tabla de
        Oferta y Utilización (TOU), Cuadro Económico Integrado (CEI), Matriz
        de Empleo e Ingresos (MEI), Matriz Insumo-Producto, and their
        methodology documents — none of which are exposed elsewhere in this
        project. Returns summaries only — pass the returned pagina_id to
        get_bce_cuentas_nacionales_archivo to read one page's file list.

        Args:
            query: Free text matched (accent-insensitive) against the
                page's title, category, or id, e.g. "trimestral", "mip",
                "regional". Empty returns all pages.
            format: text | json
        """
        try:
            result = await bce_cuentas_nacionales_client.search_cuentas_nacionales(
                query=query
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar Cuentas Nacionales del BCE: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            paginas = data.get("paginas") or []
            parts = [
                (
                    f"Cuentas Nacionales (BCE) — {data['total']} resultado(s) de "
                    f"{data['total_paginas']} páginas"
                ),
                "",
            ]
            if not paginas:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, p in enumerate(paginas, 1):
                parts.append(
                    f"{i}. {p.get('titulo')} [{p.get('categoria')}, "
                    f"{p.get('total_archivos')} archivo(s)]"
                )
                parts.append(f"   pagina_id: {p.get('pagina_id')}")
                parts.append(f"   {p.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

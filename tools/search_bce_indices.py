from mcp.server.fastmcp import FastMCP

from helpers import bce_indices_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_bce_indices_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_bce_indices(query: str = "", format: str = "text") -> str:
        """
        List BCE "índice" archive pages — one per named publication series
        (sector bulletins for petroleum/mining/cement, trade price indices,
        EMOE/confidence indices, FX buy/sell, balance of payments, weekly
        monetary bulletins, remittance bulletins, and more), each with a
        year-by-year or week-by-week file archive going back as far as 2004
        for some series.

        A dedicated catalog separate from BCEData/IEM/search_bce_publicaciones:
        these are named documents (PDF/XLSX/HTML reports) with a real
        historical archive per series, not a rolling recent-items window and
        not raw numeric series. Returns summaries only — pass the returned
        pagina_id to get_bce_indice_archivo to read one series' file list.

        Args:
            query: Free text matched (accent-insensitive) against the page's
                title or URL. Empty returns all discovered pages.
            format: text | json
        """
        try:
            result = await bce_indices_client.search_indices(query=query)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar los índices de publicaciones del BCE: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            paginas = data.get("paginas") or []
            parts = [
                (
                    f"Índices de Publicaciones (BCE) — {data['total']} resultado(s) de "
                    f"{data['total_paginas']} páginas"
                ),
                "",
            ]
            if not paginas:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, p in enumerate(paginas, 1):
                rango = p.get("rango_anios")
                rango_txt = f"{rango[0]}–{rango[1]}" if rango else "sin archivos"
                parts.append(
                    f"{i}. {p.get('titulo')} [{p.get('cadencia') or '?'}, {rango_txt}, "
                    f"{p.get('total_archivos')} archivo(s)]"
                )
                parts.append(f"   pagina_id: {p.get('pagina_id')}")
                parts.append(f"   {p.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

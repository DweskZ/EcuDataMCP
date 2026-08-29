from mcp.server.fastmcp import FastMCP

from helpers import inec_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_inec_estadisticas_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_inec_estadisticas(
        query: str = "",
        limit: int = 30,
        offset: int = 0,
        format: str = "text",
    ) -> str:
        """
        Search INEC's statistical topic pages (ecuadorencifras.gob.ec).

        Covers ~75 topics INEC publishes (IPC, ENEMDU, ENSANUT, pobreza,
        comercio exterior, cuentas nacionales, construcción, censos...),
        separate from both search_datasets (CKAN) and search_anda (INEC's
        microdata archive). This is where the actual published aggregate
        series live — technical bulletins, methodology, and full historical
        series in Excel/CSV — for operations that ANDA only catalogs as
        metadata with no downloadable microdata (e.g. price indices).

        Follow up with get_inec_estadistica_files(url) for one topic's file
        links.

        Args:
            query: Free text matched against the topic name (accent-insensitive),
                e.g. "precios", "empleo", "pobreza". Empty returns all topics.
            limit: Max results (default 30, max 100)
            offset: Pagination offset over the matched set
            format: text | json
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        try:
            result = await inec_client.search_topics(query=query, limit=limit, offset=offset)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al buscar temas de Ecuador en Cifras (INEC): {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            temas = data.get("temas") or []
            parts = [
                (
                    f"Temas de Ecuador en Cifras (INEC) — {data['total']} resultado(s) de "
                    f"{data['total_temas']} temas (mostrando {len(temas)}, offset={data['offset']})"
                ),
                "",
            ]
            if not temas:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, t in enumerate(temas, 1):
                parts.append(f"{i}. {t.get('nombre')}")
                parts.append(f"   {t.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

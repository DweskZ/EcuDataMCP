from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import bce_publicaciones_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_search_bce_publicaciones_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Buscar últimas publicaciones del BCE", annotations=READ_ONLY)
    @log_tool
    async def search_bce_publicaciones(
        query: str = "",
        formato: Literal["", "PDF", "XLSX", "XLS", "CSV", "ZIP", "HTML"] = "",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        List recent BCE publications from "Últimas Publicaciones" — named
        bulletins and reports (weekly/monthly monetary bulletins, interest-rate
        reports, sector-analysis bulletins, IEM release notices, etc.), each
        with its publication date, title, direct URL, and format.

        A dedicated catalog separate from BCEData/IEM (search_indicadores_bce,
        search_bce_iem): most of what shows up here has no equivalent numeric
        series in either — it's the BCE's own editorial feed of published
        reports, not raw data. Only the rolling window the page itself shows
        (currently the ~30 most recent publications, newest first) — there is
        no server-side pagination or date-range filter to reach further back.
        Returns direct URLs, not file contents — download them yourself or via
        download_resource.

        Args:
            query: Free text matched against the publication's title
                (accent-insensitive). Empty returns all.
            formato: Exact match against the derived format — PDF, XLSX, XLS,
                CSV, ZIP, HTML. Empty returns all formats.
            format: text | json
        """
        try:
            result = await bce_publicaciones_client.search_publicaciones(
                query=query, formato=formato
            )
        except Exception as e:
            raise ToolError(
                f"Error al consultar Últimas Publicaciones del BCE: {e}"
            ) from e

        def to_text(data: dict) -> str:
            publicaciones = data.get("publicaciones") or []
            parts = [
                (
                    f"Últimas Publicaciones (BCE) — {data['total']} resultado(s) de "
                    f"{data['total_en_pagina']} publicaciones"
                ),
                "",
            ]
            if not publicaciones:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, p in enumerate(publicaciones, 1):
                nuevo = " [NUEVO]" if p.get("nuevo") else ""
                parts.append(f"{i}. {p.get('fecha') or p.get('fecha_texto')} — {p.get('titulo')} [{p.get('formato')}]{nuevo}")
                parts.append(f"   {p.get('url')}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

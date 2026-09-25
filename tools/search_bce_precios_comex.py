from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import bce_precios_comex_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_search_bce_precios_comex_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar índices de precios de comercio exterior del BCE",
        annotations=READ_ONLY,
    )
    @log_tool
    async def search_bce_precios_comex(
        query: str = "", format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        List BCE's disaggregated foreign-trade price-index file links —
        import prices by economic-use category (fuels/lubricants, raw
        materials, consumer goods, capital goods) and export prices by
        individual product (crude oil, shrimp, banana, cacao, copper, gold,
        roses, ...), each with separate price/value/volume sheets and
        monthly/annual/cumulative variation sheets.

        Genuinely distinct from search_indicadores_bce's BCEData catalog
        (id_grupo 134 "Índices IPX - IPM - ITI" only has the three
        *aggregate* series — general export index, general import index,
        ITI) and from search_bce_indices (a different, year-archived
        widget that doesn't cover trade prices). Returns direct URLs, not
        file contents — download them yourself or via download_resource.

        Args:
            query: Free text matched against the file's label, page title,
                or page id (accent-insensitive), e.g. "importacion",
                "exportacion". Empty returns all files.
            format: text | json
        """
        try:
            result = await bce_precios_comex_client.search_archivos(query=query)
        except Exception as e:
            raise ToolError(
                f"Error al consultar Índices de Precios de Comercio Exterior del BCE: {e}"
            ) from e

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"Índices de Precios de Comercio Exterior (BCE) — {data['total']} "
                    f"resultado(s) de {data['total_en_paginas']} archivos"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, f in enumerate(archivos, 1):
                parts.append(f"{i}. {f.get('label')} [{f.get('format')}] — {f.get('pagina_titulo')}")
                parts.append(f"   {f.get('url')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

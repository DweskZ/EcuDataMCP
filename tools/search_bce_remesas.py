from mcp.server.fastmcp import FastMCP

from helpers import bce_remesas_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_bce_remesas_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_bce_remesas(query: str = "", format: str = "text") -> str:
        """
        List BCE's Remesas de Trabajadores (worker remittances) direct file links.

        A dedicated series separate from BCEData/IEM (search_indicadores_bce,
        search_bce_iem): the aggregate flow series, the full historical
        series, a methodology user note, and — since a July 2025 change to
        microdata-based collection — monthly aggregate and entity-level
        databases (BDD). Treat "histórica" (pre-change) and "BDD"
        (post-change) files as methodologically distinct series, not one
        continuous one — see the user note (Nota_al_usuario) for the
        comparability details. Returns direct URLs, not file contents —
        download them yourself or via download_resource.

        Args:
            query: Free text matched against the file's label or URL
                (accent-insensitive), e.g. "historica", "entidad", "bdd".
                Empty returns all files.
            format: text | json
        """
        try:
            result = await bce_remesas_client.search_archivos(query=query)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar Remesas de Trabajadores del BCE: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"Remesas de Trabajadores (BCE) — {data['total']} resultado(s) de "
                    f"{data['total_en_pagina']} archivos"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, f in enumerate(archivos, 1):
                parts.append(f"{i}. {f.get('label')} [{f.get('format')}]")
                parts.append(f"   {f.get('url')}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

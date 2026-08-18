from mcp.server.fastmcp import FastMCP

from helpers import sri_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_sri_datasets_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_sri_datasets(
        query: str = "",
        limit: int = 30,
        offset: int = 0,
        format: str = "text",
    ) -> str:
        """
        Search the SRI's open datasets page (sri.gob.ec/datasets) for direct file links.

        Covers ~130 CSV/XLSX/ZIP files not reachable through search_datasets
        (they live on the SRI's own site, not the CKAN DataStore): RUC catastro
        by province, recaudación by year, ventas/compras, vehículos nuevos,
        comprobantes electrónicos (CEL), inscripciones/cierres, plus variable
        dictionaries (*_DD.xlsx). Returns direct URLs, not the file contents —
        download them yourself or via download_resource.

        Args:
            query: Free text matched against the file's label or URL
                (accent-insensitive), e.g. "recaudación", "vehiculos", "Pichincha".
                Empty returns all files.
            limit: Max results (default 30, max 100)
            offset: Pagination offset over the matched set
            format: text | json
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        try:
            result = await sri_client.search_files(query=query, limit=limit, offset=offset)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar los datasets del SRI: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"Datasets del SRI — {data['total']} resultado(s) de "
                    f"{data['total_en_pagina']} archivos "
                    f"(mostrando {len(archivos)}, offset={data['offset']})"
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

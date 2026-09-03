from mcp.server.fastmcp import FastMCP

from helpers import cnig_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_cnig_femicidios_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_cnig_femicidios(query: str = "", format: str = "text") -> str:
        """
        List CNIG's (Consejo Nacional para la Igualdad de Género) "Violencia"
        page statistical PDFs — includes the femicide / intentional-
        homicide-of-women matrix ("Femicidios y Homicidios Intencionales de
        Mujeres") plus 19 related gender-violence tables (by province,
        ethnicity, disability, age, income quintile, LGBTI, judicialized
        cases, etc.) from the same page.

        Institution note: this is CNIG (the gender-equality council), not
        Fiscalía General del Estado — a different institution that also
        publishes femicide figures elsewhere. The PDF itself states its
        figures are compiled from Consejo de la Judicatura, Fiscalía
        General del Estado, and Ministerio del Interior source data, and
        describes the underlying indicator as updated weekly — but the
        PDF actually posted on this page is a dated snapshot (content
        cut-off April 2023), not a live rolling feed, so treat "weekly" as
        the institution's stated intent rather than a guarantee about
        what's currently posted. Returns direct URLs to PDFs, not parsed
        table data — download them yourself, via download_resource, or
        via read_pdf.

        Args:
            query: Free text matched against the entry's label
                (accent-insensitive), e.g. "femicidio", "lgbti", "provincia".
                Empty returns all 20 entries on the page.
            format: text | json
        """
        try:
            result = await cnig_client.search_femicidios(query=query)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar la página de Violencia del CNIG: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"CNIG — Violencia — {data['total']} resultado(s) de "
                    f"{data['total_en_pagina']} entradas"
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

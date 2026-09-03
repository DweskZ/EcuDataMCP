from mcp.server.fastmcp import FastMCP

from helpers import infomies_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_infomies_bases_mensuales_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_infomies_bases_mensuales(
        serie: str, anio: int | None = None, query: str = "", format: str = "text"
    ) -> str:
        """
        List infoMIES's (info.desarrollohumano.gob.ec, the statistics portal
        of what used to be MIES) monthly BDD (base de datos) files for one
        program: "anc" (Aseguramiento No Contributivo / inclusión económica)
        or "is" (Usuarios de Unidad de Atención del SIIMIES / inclusión
        social). Richer than this project's existing CKAN coverage for the
        same programs (organization=ministerio-de-inclusion-economica-y-
        social), which only has quarterly snapshots.

        Confirmed live 2026-09-03: only the current, in-progress year has
        one file per month so far published; every closed year (2019-2025
        for "anc", 2019-2025 for "is") has exactly ONE file, the December/
        year-end snapshot -- don't assume every year is a 12-file monthly
        archive. Files are .rar (this project's format-support decision
        excludes reading .rar -- subprocess/CVE risk -- so only metadata +
        the direct URL are returned here, not contents); fetch the URL
        yourself if you need the bytes.

        Args:
            serie: "anc" or "is".
            anio: Specific year to fetch, e.g. 2024. Omit to fetch every
                known year for the series and aggregate (multiple requests
                on a cold cache -- prefer passing anio when you know it).
            query: Free text matched (accent-insensitive) against the
                file's label, year, or URL, e.g. "julio", "2023". Empty
                returns all files for the selected year(s).
            format: text | json
        """
        try:
            result = await infomies_client.search_bases_mensuales(
                serie=serie, anio=anio, query=query
            )
        except ValueError as e:
            return render_output(
                {"error": str(e), "serie": serie, "anio": anio},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "serie": serie, "anio": anio},
                format,
                text_builder=lambda d: f"Error al consultar infoMIES: {d['error']}",
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"{data.get('source')} — {data['total']} resultado(s) de "
                    f"{data['total_en_pagina']} archivo(s)"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, f in enumerate(archivos, 1):
                parts.append(f"{i}. [{f.get('anio')}] {f.get('label')} [{f.get('format')}]")
                parts.append(f"   {f.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

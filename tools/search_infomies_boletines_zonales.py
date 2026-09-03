from mcp.server.fastmcp import FastMCP

from helpers import infomies_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_infomies_boletines_zonales_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_infomies_boletines_zonales(
        modo: str = "zonal",
        zona: str = "",
        anio: int | None = None,
        query: str = "",
        format: str = "text",
    ) -> str:
        """
        List infoMIES's (info.desarrollohumano.gob.ec) zonal bulletin files.
        Two distinct series live under this name, confirmed live 2026-09-03
        -- pick one with `modo`:

        - modo="zonal" (default): the original "Boletín Zonal" series, one
          .rar per zone per month. DISCONTINUED -- confirmed range
          2017-2021 across all 9 zones, nothing since. Requires `zona`
          (get valid keys from the same tool with modo="zonal" and no zona,
          or use "zona-1-bz".."zona-9-bz" directly).
        - modo="consolidado": the newer "Reporte Boletines Zonales"
          successor -- one consolidated XLSX per year, 2021-2026, STILL
          BEING UPDATED (unlike the zonal series). `zona` is ignored in
          this mode.

        Both series are large files (the zonal .rar are small per file but
        there are ~9 zones x ~5 years x ~11 months of them; the consolidado
        XLSX are 9-15 MB each) -- this tool returns metadata + direct URLs
        only, never file contents. The .rar files are additionally out of
        this project's supported-format list (subprocess/CVE risk) even at
        a size that would otherwise fit.

        Args:
            modo: "zonal" or "consolidado".
            zona: Required for modo="zonal": one of "zona-1-bz".."zona-9-bz".
                Ignored for modo="consolidado". Leave empty with
                modo="zonal" to just get the list of valid zone keys.
            anio: Specific year to fetch. For "zonal", omit to fetch every
                year found on that zone's index page (typically 2017-2021).
                For "consolidado", omit to fetch 2021-2026. Either way,
                omitting means multiple HTTP requests on a cold cache.
            query: Free text matched (accent-insensitive) against the
                file's label, year, or URL.
            format: text | json
        """
        if modo not in ("zonal", "consolidado"):
            return render_output(
                {"error": "modo debe ser 'zonal' o 'consolidado'", "modo": modo},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        if modo == "consolidado":
            try:
                result = await infomies_client.search_reportes_boletines_zonales(
                    anio=anio, query=query
                )
            except ValueError as e:
                return render_output(
                    {"error": str(e), "anio": anio},
                    format,
                    text_builder=lambda d: f"Error: {d['error']}",
                )
            except Exception as e:
                return render_output(
                    {"error": str(e), "anio": anio},
                    format,
                    text_builder=lambda d: (
                        f"Error al consultar los Reportes Boletines Zonales de infoMIES: {d['error']}"
                    ),
                )

            def to_text_consolidado(data: dict) -> str:
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

            return render_output(result, format, text_builder=to_text_consolidado)

        # modo == "zonal"
        if not zona:
            zonas = infomies_client.list_zonas()
            return render_output(
                {"zonas": zonas},
                format,
                text_builder=lambda d: (
                    "Zonas válidas para modo='zonal': " + ", ".join(d["zonas"])
                ),
            )

        try:
            result = await infomies_client.get_boletines_zonales(
                zona=zona, anio=anio, query=query
            )
        except ValueError as e:
            return render_output(
                {"error": str(e), "zona": zona, "anio": anio},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "zona": zona, "anio": anio},
                format,
                text_builder=lambda d: (
                    f"Error al consultar los Boletines Zonales de infoMIES: {d['error']}"
                ),
            )

        def to_text_zonal(data: dict) -> str:
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

        return render_output(result, format, text_builder=to_text_zonal)

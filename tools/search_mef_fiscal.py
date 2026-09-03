from mcp.server.fastmcp import FastMCP

from helpers import mef_fiscal_client
from helpers.format_out import render_output
from helpers.logging import log_tool

_FUENTES = {"mef", "senae"}


def register_search_mef_fiscal_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_mef_fiscal(
        fuente: str = "mef", query: str = "", format: str = "text"
    ) -> str:
        """
        List Ecuador's fiscal-operations workbook links from either of two
        sources — MEF/MDEP (primary, current) or SENAE (secondary, stale).

        fuente="mef" (default): Ministerio de Economía y Finanzas / MDEP's
        "Estadística Nueva Metodología" archive — IMF GFSM-methodology SPNF
        (Sector Público No Financiero) fiscal accounts, updated monthly.
        NOT one static workbook: 76 XLSX files confirmed live (income/
        expense and assets/liabilities snapshots, each numbered per
        publication, plus "BLL"/financing files), publication folders from
        2025-01 through 2026-09. For tariff income specifically, download
        the newest "Operaciones de Ingresos y Gastos SPNF" file and read row
        "1214 Arancelarios" (within "121 Ingresos tributarios", sheet "GC" =
        Gobierno Central) — annual series 2013-2025 plus quarterly
        breakdown confirmed in a prior pass (2023 = USD 1,180.4M, 2024 =
        USD 1,117.3M, 2025 = USD 1,231.4M).

        fuente="senae": SENAE's "Tributos Recaudados" archive — 60 XLSX
        files confirmed live, but stale (2012-2021 only, nothing since).
        Breaks customs collection down by ADVALOREM/FODINFA/IVA/ICE/OTROS
        TRIBUTOS/TOTALES per year — useful for the category breakdown MEF
        doesn't expose this cheaply, despite being frozen at 2021.

        IMPORTANT scope distinction: "Arancelarios" (MEF) and "ADVALOREM"
        (SENAE) are the tariff/derecho aduanero ALONE — smaller than the
        ~USD 3,776M press coverage cites for 2024 "recaudación aduanera",
        which also includes IVA and ICE collected at the border. Use
        "Arancelarios"/"ADVALOREM" for tariff revenue narrowly; use SENAE's
        TOTALES category (2012-2021 only) or sum the individual lines for
        the broader "everything Aduana collects" figure.

        Returns direct URLs to XLSX files, not parsed table data — download
        them yourself or via download_resource, then read with the xlsx
        skill.

        Args:
            fuente: "mef" (default) or "senae".
            query: Free text matched (accent-insensitive) against the
                file's label (and, for "senae", its category too), e.g.
                "ingresos", "2026-06", "advalorem", "totales". Empty
                returns all files for the chosen fuente.
            format: text | json
        """
        fuente_norm = (fuente or "mef").strip().lower()
        if fuente_norm not in _FUENTES:
            return render_output(
                {"error": f"fuente '{fuente}' no reconocida. Válidas: mef, senae"},
                format,
                text_builder=lambda d: d["error"],
            )

        try:
            if fuente_norm == "senae":
                result = await mef_fiscal_client.search_senae_tributos(query=query)
            else:
                result = await mef_fiscal_client.search_operaciones_spnf(query=query)
        except Exception as e:
            return render_output(
                {"error": str(e), "fuente": fuente_norm, "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar la fuente fiscal '{d['fuente']}': {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"{data['source']} — {data['total']} resultado(s) de "
                    f"{data['total_en_pagina']} archivos"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, f in enumerate(archivos, 1):
                detalle = ""
                if "carpeta_publicacion" in f:
                    detalle = f" (publicado {f['carpeta_publicacion']})"
                elif "categoria" in f:
                    anio = f.get("anio")
                    detalle = f" [{f['categoria']}{', ' + str(anio) if anio else ''}]"
                parts.append(f"{i}. {f.get('label')}{detalle} [{f.get('format')}]")
                parts.append(f"   {f.get('url')}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

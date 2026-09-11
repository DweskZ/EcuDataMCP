from mcp.server.mcpserver import MCPServer

from helpers import senescyt_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_senescyt_estadisticas_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def search_senescyt_estadisticas(query: str = "", format: str = "text") -> str:
        """
        List SENESCYT's SIAU higher-education/science-technology-innovation
        (CTI) statistics reports: methodology sheets, annual indicator
        reports (2021/2022/2024), the national competitiveness index, the
        CTI/ancestral-knowledge indicator inventory, labor-demand
        characterization, and the COVID-19 impact study on higher education.

        Separate from this project's existing SENESCYT coverage: the CKAN
        organization datasets (matrícula, docentes, becarios), the
        captcha-gated título registry (not automatable, by policy), and
        MINEDEC's basic-education matrícula (search_minedec_matricula).
        Each file's "tipo" is "wpdm" (a WordPress Download Manager gateway
        link — real but with no visible file extension, "formato" is
        reported as DESCONOCIDO) or "directo" (a same-origin file or a
        Nextcloud share link on cloud-00/cloud-pro.senescyt.gob.ec).

        Args:
            query: Free text matched (accent-insensitive) against the
                file's seccion, titulo, tipo ("wpdm"/"directo"), or URL.
                Empty returns all files.
            format: text | json
        """
        try:
            result = await senescyt_client.search_estadisticas(query=query)
        except Exception as e:
            return render_output(
                {"error": str(e), "query": query or None},
                format,
                text_builder=lambda d: (
                    f"Error al consultar las Estadísticas de Educación Superior de "
                    f"SENESCYT: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"SENESCYT — SIAU, Estadísticas de Educación Superior, CTI — "
                    f"{data['total']} resultado(s) de {data['total_en_pagina']} archivos"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, f in enumerate(archivos, 1):
                meta_bits = [f.get("tipo"), f.get("formato")]
                if f.get("tamano"):
                    meta_bits.append(f["tamano"])
                if f.get("actualizado"):
                    meta_bits.append(f["actualizado"])
                parts.append(f"{i}. {f.get('titulo')} [{', '.join(b for b in meta_bits if b)}]")
                parts.append(f"   Sección: {f.get('seccion')}")
                parts.append(f"   {f.get('url')}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

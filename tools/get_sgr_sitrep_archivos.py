from mcp.server.fastmcp import FastMCP

from helpers import sgr_publicaciones_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_sgr_sitrep_archivos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_sgr_sitrep_archivos(evento_url: str, format: str = "text") -> str:
        """
        List the SITREP PDF report links published on one SGR adverse-event
        page.

        Get evento_url from search_sgr_sitreps's "url" field. Returns each
        report's grupo (the page's own section heading, e.g. "SITREP
        NACIONALES", "SITREP PROVINCIALES – AZUAY", when the page
        separates national/provincial/cantonal reports), titulo, and
        direct PDF URL — not the file contents. A long-running event (e.g.
        an ongoing rainy season) can carry 700+ PDFs across national,
        provincial, and cantonal reports plus matching "Infografía"
        summaries; a closed single-incident event (e.g. one earthquake)
        usually has far fewer. Download the URL directly, or via
        download_resource / read_pdf.

        Args:
            evento_url: An event URL from search_sgr_sitreps's "url" field
                (must be on gestionderiesgos.gob.ec).
            format: text | json
        """
        try:
            result = await sgr_publicaciones_client.get_sitrep_archivos(evento_url)
        except ValueError as e:
            return render_output(
                {"error": str(e), "evento_url": evento_url},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "evento_url": evento_url},
                format,
                text_builder=lambda d: (
                    f"Error al obtener la página de evento SITREP de SGR: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [f"Evento SITREP SGR: {data.get('url')}", ""]
            if not archivos:
                parts.append("No se encontraron reportes PDF en esta página.")
                return "\n".join(parts)
            parts.append(f"{data['total']} reporte(s):")
            for a in archivos:
                etiqueta = " / ".join(p for p in (a.get("grupo"), a.get("titulo")) if p)
                parts.append(f"- {etiqueta}")
                parts.append(f"   {a.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

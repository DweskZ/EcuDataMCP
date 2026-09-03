from mcp.server.fastmcp import FastMCP

from helpers import seps_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_seps_seccion_archivos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_seps_seccion_archivos(seccion: str, format: str = "text") -> str:
        """
        List the direct download links published on one SEPS statistics
        section page (estadisticas.seps.gob.ec).

        Get the seccion key from list_seps_secciones. Returns the
        section's own short description plus each file's grupo (a
        sub-heading some sections split entries under, e.g. cooperative
        segments 1-3 vs 4-5 -- None where the section has no such split),
        periodo/titulo (the published period label, e.g. "2026", "Años
        anteriores", or "2026 con corte al 31 de marzo" for the latest
        entry), direct URL, and format -- not the file contents.

        Some links are direct static PDF/ZIP URLs; others go through the
        site's "Simple Download Monitor" plugin
        (?sdm_process_download=1&download_id=N) and redirect (302) to the
        same kind of static file when fetched -- format comes back
        DESCONOCIDO for those since the download-monitor URL itself
        carries no extension. Download the URL directly rather than
        routing it through preview_resource_data or download_resource,
        which cap at 5 MB.

        Args:
            seccion: A section key from list_seps_secciones, e.g.
                "sfps_reportes_calificacion_de_riesgos".
            format: text | json
        """
        try:
            result = await seps_client.get_seccion_archivos(seccion)
        except ValueError as e:
            return render_output(
                {"error": str(e), "seccion": seccion},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "seccion": seccion},
                format,
                text_builder=lambda d: f"Error al obtener la sección SEPS: {d['error']}",
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [f"Sección SEPS: {data.get('nombre')}", f"URL: {data.get('url')}"]
            if data.get("descripcion"):
                parts.append(data["descripcion"])
            parts.append("")
            if not archivos:
                parts.append("No se encontraron archivos descargables en esta página.")
                return "\n".join(parts)
            parts.append(f"{len(archivos)} archivo(s):")
            for a in archivos:
                etiqueta = " / ".join(
                    p for p in (a.get("grupo"), a.get("periodo"), a.get("titulo")) if p
                )
                parts.append(f"- {etiqueta} [{a.get('formato')}]")
                parts.append(f"   {a.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

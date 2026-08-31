from mcp.server.fastmcp import FastMCP

from helpers import superbancos_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_superbancos_seccion_archivos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_superbancos_seccion_archivos(seccion: str, format: str = "text") -> str:
        """
        List the direct download links published on one Superbancos
        statistics section page.

        Get the seccion key from list_superbancos_secciones. Returns each
        file's grupo (table section, e.g. "TARJETAS DE CRÉDITO"), periodo
        (year label, when the table separates it from the file title),
        titulo, direct URL, and format — not the file contents. Files can
        be several MB; download the URL directly instead of routing it
        through preview_resource_data or download_resource, which cap at
        5 MB.

        Coverage stops where the page's static archive tables stop — most
        recent years live in a client-side OneDrive widget this tool does
        not read. Do not present the newest "periodo"/"titulo" found here
        as the most recent data available from Superbancos.

        Args:
            seccion: A section key from list_superbancos_secciones, e.g.
                "boletines_financieros", "servicios_financieros",
                "informacion_historica", "calendario_estadistico".
            format: text | json
        """
        try:
            result = await superbancos_client.get_seccion_archivos(seccion)
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
                text_builder=lambda d: f"Error al obtener la sección Superbancos: {d['error']}",
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [f"Sección Superbancos: {data.get('nombre')}", f"URL: {data.get('url')}", ""]
            if not archivos:
                parts.append("No se encontraron archivos descargables en esta página.")
                return "\n".join(parts)
            parts.append(f"{len(archivos)} archivo(s):")
            for a in archivos:
                etiqueta = " / ".join(
                    p for p in (a.get("grupo"), a.get("periodo"), a.get("titulo")) if p
                )
                parts.append(f"- {etiqueta} [{a.get('formato')}]")
                if a.get("descripcion"):
                    parts.append(f"   {a['descripcion']}")
                parts.append(f"   {a.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

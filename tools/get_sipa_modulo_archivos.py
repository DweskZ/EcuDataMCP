from mcp.server.fastmcp import FastMCP

from helpers import sipa_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_sipa_modulo_archivos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_sipa_modulo_archivos(modulo: str, format: str = "text") -> str:
        """
        List the direct download links published on one SIPA statistics module.

        Get the modulo key from list_sipa_modulos. Returns each file's
        title, description, direct XLSX/XLS URL, and format — not the file
        contents. Files can be large (one confirmed at 41 MB); download the
        URL directly instead of routing it through preview_resource_data or
        download_resource, which cap at 5 MB.

        Args:
            modulo: A module key from list_sipa_modulos, e.g. "economico",
                "productivo", "social", "censos".
            format: text | json
        """
        try:
            result = await sipa_client.get_modulo_archivos(modulo)
        except ValueError as e:
            return render_output(
                {"error": str(e), "modulo": modulo},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "modulo": modulo},
                format,
                text_builder=lambda d: f"Error al obtener el módulo SIPA: {d['error']}",
            )

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [f"Módulo SIPA: {data.get('nombre')}", f"URL: {data.get('url')}", ""]
            if not archivos:
                parts.append("No se encontraron archivos descargables en esta página.")
                return "\n".join(parts)
            parts.append(f"{len(archivos)} archivo(s):")
            for a in archivos:
                parts.append(f"{a.get('numero')}. {a.get('titulo')} [{a.get('formato')}]")
                parts.append(f"   {a.get('descripcion')}")
                parts.append(f"   {a.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

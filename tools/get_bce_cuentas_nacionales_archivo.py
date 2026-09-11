from mcp.server.mcpserver import MCPServer

from helpers import bce_cuentas_nacionales_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_bce_cuentas_nacionales_archivo_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def get_bce_cuentas_nacionales_archivo(
        pagina_id: str, max_archivos: int = 50, format: str = "text"
    ) -> str:
        """
        Read the file list for one BCE Cuentas Nacionales page (from
        search_bce_cuentas_nacionales).

        Each item is one published file (report, data package, or
        methodology document) with a label, direct URL, and format. Returns
        direct URLs, not file contents — download them yourself or via
        download_resource.

        Args:
            pagina_id: The page's id, from search_bce_cuentas_nacionales'
                `pagina_id` field (e.g. "boletin-de-cuentas-nacionales-trimestrales").
            max_archivos: Cap on returned files, 1-200.
            format: text | json
        """
        try:
            result = await bce_cuentas_nacionales_client.get_archivo(
                pagina_id=pagina_id, max_archivos=max_archivos
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "pagina_id": pagina_id},
                format,
                text_builder=lambda d: (
                    f"Error al leer la página de Cuentas Nacionales '{d['pagina_id']}' del BCE: {d['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            pagina = data.get("pagina") or {}
            archivos = data.get("archivos") or []
            parts = [
                f"{pagina.get('titulo')} ({pagina.get('categoria')})",
                (
                    f"{data['archivos_mostrados']} de {data['total_archivos']} archivo(s)"
                    + (" [truncado]" if data.get("truncado") else "")
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin archivos.")
                return "\n".join(parts)
            for a in archivos:
                parts.append(f"- {a['label']} [{a['format']}]")
                parts.append(f"   {a['url']}")
            parts.append("")
            parts.append(f"Fuente: {pagina.get('url')}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

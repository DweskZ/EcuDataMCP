from mcp.server.fastmcp import FastMCP

from helpers import contraloria_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_contraloria_informes_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_contraloria_informes(format: str = "text") -> str:
        """
        List Contraloría General del Estado's "Datos Abiertos" documents.

        Quarterly CSV exports of audit reports approved for ANY public
        institution in the country (Unidad de Control, Entidad, Diligencia,
        periodo, tipo de informe, N° de informe, fecha de aprobación) —
        much broader than any single-institution audit archive already
        covered elsewhere in this MCP. New quarters are added roughly every
        three months.

        Follow up with get_contraloria_informe(informe_id) for one
        document's parsed rows.

        Args:
            format: text | json
        """
        try:
            informes = await contraloria_client.list_informes()
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: (
                    f"Error al listar documentos de Datos Abiertos de la Contraloría: {d['error']}"
                ),
            )

        def to_text(data: list[dict]) -> str:
            parts = [f"Documentos de Datos Abiertos de la Contraloría — {len(data)}:", ""]
            if not data:
                parts.append("No se encontraron documentos.")
                return "\n".join(parts)
            for i in data:
                parts.append(f"- id={i['id']}: {i['label']}")
                parts.append(f"  {i['url']}")
            return "\n".join(parts)

        return render_output(informes, format, text_builder=to_text)

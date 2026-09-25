from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import contraloria_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_list_contraloria_informes_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Listar informes de datos abiertos de Contraloría", annotations=READ_ONLY
    )
    @log_tool
    async def list_contraloria_informes(
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        List Contraloría General del Estado's "Datos Abiertos" and
        "Plan Anual de Control" documents.

        "Datos Abiertos" are quarterly CSV exports of audit reports approved
        for ANY public institution in the country (Unidad de Control,
        Entidad, Diligencia, periodo, tipo de informe, N° de informe, fecha
        de aprobación) — much broader than any single-institution audit
        archive already covered elsewhere in this MCP. New quarters are
        added roughly every three months. "Plan Anual de Control" documents
        are one PDF per year (the approved annual control plan).

        Follow up with get_contraloria_informe(informe_id) for one
        document's parsed rows (CSV) or metadata + read_pdf pointer (PDF).

        Args:
            format: text | json
        """
        try:
            informes = await contraloria_client.list_informes()
        except Exception as e:
            raise ToolError(
                f"Error al listar documentos de Datos Abiertos de la Contraloría: {e}"
            ) from e

        payload = {"total": len(informes), "informes": informes}

        def to_text(data: dict) -> str:
            rows = data["informes"]
            parts = [f"Documentos de Datos Abiertos de la Contraloría — {len(rows)}:", ""]
            if not rows:
                parts.append("No se encontraron documentos.")
                return "\n".join(parts)
            for i in rows:
                parts.append(f"- id={i['id']}: {i['label']}")
                parts.append(f"  {i['url']}")
            return "\n".join(parts)

        return render_structured(payload, format, text_builder=to_text)

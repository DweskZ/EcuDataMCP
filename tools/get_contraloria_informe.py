from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import contraloria_client
from helpers.csv_reader import format_table
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_contraloria_informe_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Ver un informe de datos abiertos de Contraloría", annotations=READ_ONLY)
    @log_tool
    async def get_contraloria_informe(
        informe_id: str, rows: int = 50, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        Download and preview one Contraloría document (Datos Abiertos or
        Plan Anual de Control).

        Get informe_id from list_contraloria_informes. Quarterly "Datos
        Abiertos" documents return one row per audit report approved that
        quarter, across every public institution in the country. "Plan
        Anual de Control" documents are PDFs (one per year); this returns
        their metadata and points you at read_pdf instead of a table.

        Args:
            informe_id: An id from list_contraloria_informes
            rows: Number of data rows to preview (default: 50, max: 200)
            format: text | json
        """
        rows = min(max(rows, 1), 200)

        try:
            result = await contraloria_client.get_informe(informe_id, max_rows=rows)
        except ValueError as e:
            raise ToolError(f"Error: {e}") from e
        except Exception as e:
            raise ToolError(f"Error al descargar el documento: {e}") from e

        if result.get("is_pdf"):
            return render_structured(
                result,
                format,
                text_builder=lambda d: (
                    f"Documento: {d['label']}\n"
                    f"URL: {d['url']}\n"
                    "Este documento es un PDF, no una tabla -- usa "
                    f"read_pdf('{d['url']}') para leer su contenido."
                ),
            )

        headers = result["headers"]
        if not headers:
            # Ambiguous case (Phase 3 migration): the document was fetched
            # successfully, but came back empty or unparseable -- left as a
            # normal response rather than ToolError since this may reflect
            # the source file's own content, not an execution failure.
            return render_structured(
                {"error": "vacio", "informe_id": informe_id, "label": result.get("label")},
                format,
                text_builder=lambda d: (
                    f"El documento '{d['label']}' está vacío o no pudo ser parseado."
                ),
            )

        def to_text(data: dict) -> str:
            parts = [
                f"Documento: {data['label']}",
                f"URL: {data['url']}",
                f"Columnas: {len(data['headers'])}",
                f"Filas mostradas: {data['total_rows_in_preview']}",
            ]
            if data.get("truncated"):
                parts.append("⚠ Archivo truncado (excede 5 MB o tiene más filas)")
            parts.append("")
            parts.append(format_table(data["headers"], data["rows"]))
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

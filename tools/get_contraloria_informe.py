from mcp.server.fastmcp import FastMCP

from helpers import contraloria_client
from helpers.csv_reader import format_table
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_contraloria_informe_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_contraloria_informe(
        informe_id: str, rows: int = 50, format: str = "text"
    ) -> str:
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
            return render_output(
                {"error": str(e), "informe_id": informe_id},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e), "informe_id": informe_id},
                format,
                text_builder=lambda d: f"Error al descargar el documento: {d['error']}",
            )

        if result.get("is_pdf"):
            return render_output(
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
            return render_output(
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

        return render_output(result, format, text_builder=to_text)

import logging

from mcp.server.fastmcp import FastMCP

from helpers import bce_iem_client
from helpers.format_out import render_output
from helpers.logging import MAIN_LOGGER_NAME, log_tool

logger = logging.getLogger(MAIN_LOGGER_NAME)


def register_get_bce_iem_table_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_bce_iem_table(
        table_id: str,
        desde: str = "",
        hasta: str = "",
        boletin_numero: int = 0,
        rows: int = 20,
        format: str = "text",
    ) -> str:
        """Inspect one official XLSX table from the latest BCE IEM bulletin.

        Get table_id from search_bce_iem. Tables with the common BCE layout
        (periods across columns and variables down rows) return structured,
        date-filterable series. Other layouts return a faithful preview
        rather than silently guessing columns. Always includes the BCE file
        and bulletin URLs for verification. Pass boletin_numero to retrieve
        a historical version returned by search_bce_iem(historico=true).
        """
        rows = min(max(rows, 1), 100)
        try:
            result = await bce_iem_client.get_table(
                table_id, desde, hasta, rows, boletin_numero
            )
        except Exception as exc:
            logger.exception("get_bce_iem_table failed (table_id=%r)", table_id)
            return render_output(
                {"error": str(exc), "table_id": table_id},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        def to_text(data: dict) -> str:
            table = data["tabla"]
            parts = [
                table["titulo"],
                f"table_id: {table['table_id']}",
                f"Fuente: {table['url']}",
                "",
            ]
            if data["formato"] == "series_ancho":
                parts.append("Períodos: " + ", ".join(data["periodos"]))
                parts.append("")
                for block in data["bloques"]:
                    parts.append(block["unidad"])
                    for series in block["series"]:
                        values = " | ".join(
                            f"{period}: {value}"
                            for period, value in series["valores"].items()
                        )
                        parts.append(f"{series['nombre']}: {values}")
                    if block["truncada"]:
                        parts.append("[Series adicionales no mostradas]")
                    parts.append("")
                return "\n".join(parts)

            if data["formato"] == "tabla_larga":
                parts.append(" | ".join(data["encabezados"]))
                for row in data["filas"]:
                    parts.append(" | ".join(row))
                if data["truncada"]:
                    parts.append(
                        f"[Vista truncada: {data['filas_totales']} filas coincidentes]"
                    )
                return "\n".join(parts)

            for sheet in data["hojas"]:
                parts.append(f"Hoja: {sheet['nombre']}")
                for row in sheet["vista"]:
                    parts.append(" | ".join(row))
                if sheet["truncada"]:
                    parts.append("[Vista truncada]")
                parts.append("")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

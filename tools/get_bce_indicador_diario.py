from mcp.server.fastmcp import FastMCP

from helpers import bce_indicadores_diarios_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_bce_indicador_diario_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_bce_indicador_diario(
        archivo: str,
        codigo: str,
        ultimos_n: int = 30,
        desde: str = "",
        hasta: str = "",
        format: str = "text",
    ) -> str:
        """
        Fetch one BCE daily/monthly indicator's time series (e.g. Riesgo
        País), bounded to a window — never the full series (some run
        7,000+ observations).

        Get archivo/codigo from list_bce_indicadores_diarios first — a
        codigo only means one thing within its own archivo. Without
        desde/hasta, returns the most recent ultimos_n observations
        (capped at 366). With desde/hasta (YYYY-MM-DD, inclusive), returns
        that date range instead, also capped at 366 rows (most recent
        within the range if it's larger). The response always includes
        rango_completo (the series' true full date range and row count)
        so the window returned is never mistaken for the whole series.

        Args:
            archivo: A file name from list_bce_indicadores_diarios.
            codigo: A "Código Variable Dinámica" from that same archivo.
            ultimos_n: Most recent N observations when no date range is given.
            desde: Optional start date YYYY-MM-DD.
            hasta: Optional end date YYYY-MM-DD.
            format: text | json
        """
        try:
            result = await bce_indicadores_diarios_client.get_indicador_diario(
                archivo, codigo, ultimos_n=ultimos_n, desde=desde or None, hasta=hasta or None
            )
        except ValueError as e:
            return render_output(
                {"error": str(e), "archivo": archivo, "codigo": codigo},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        def to_text(data: dict) -> str:
            rc = data["rango_completo"]
            parts = [
                f"{data['indicador']} ({data['archivo']} / {data['codigo']})",
                f"Periodicidad: {data['periodicidad']}  ·  Unidad: {data['unidad']}",
                f"Rango completo: {rc['desde']} a {rc['hasta']} ({rc['n_datos']} datos totales)",
                "",
            ]
            datos = data.get("datos") or []
            if not datos:
                parts.append("Sin datos en la ventana solicitada.")
                return "\n".join(parts)
            parts.append(f"Ventana devuelta ({len(datos)} dato(s)):")
            for d in datos:
                parts.append(f"  {d['fecha']}: {d['valor']}")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

import logging

from mcp.server.fastmcp import FastMCP

from helpers import bce_client
from helpers.format_out import render_output
from helpers.logging import MAIN_LOGGER_NAME, log_tool

logger = logging.getLogger(MAIN_LOGGER_NAME)


def register_get_indicador_bce_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_indicador_bce(
        id_grupo: int,
        desde: str = "",
        hasta: str = "",
        frecuencia: str = "",
        unidad: str = "",
        format: str = "text",
    ) -> str:
        """
        Time series data for one Banco Central del Ecuador (BCE) indicator group.

        Use search_indicadores_bce first to find the id_grupo. Frequency
        and unit vary by group (e.g. "Mensual"/"Millones de USD" for money
        supply, "Trimestral"/"Porcentaje" for GDP growth) — omit them to
        get the group's default, or check the error message for the valid
        options if you guess wrong.

        Args:
            id_grupo: The group id from search_indicadores_bce.
            desde: Start period as YYYY-MM. Defaults to the earliest
                available period for the chosen frequency.
            hasta: End period as YYYY-MM. Defaults to the latest available
                period for the chosen frequency.
            frecuencia: Semanal | Mensual | Trimestral | Anual. Defaults to
                the group's first available frequency.
            unidad: Varies by group (e.g. "Millones de USD", "Indice",
                "Porcentaje"). Defaults to the first one available for the
                chosen frequency.
            format: text | json
        """
        try:
            result = await bce_client.get_indicador(
                id_grupo=id_grupo,
                desde=desde,
                hasta=hasta,
                frecuencia=frecuencia,
                unidad=unidad,
            )
        except Exception as e:
            logger.exception("get_indicador_bce failed (id_grupo=%r)", id_grupo)
            return render_output(
                {"error": str(e), "id_grupo": id_grupo},
                format,
                text_builder=lambda d: (
                    f"Error al consultar el indicador del BCE: {d['error']}"
                ),
            )

        if result.get("error"):
            return render_output(
                result,
                format,
                text_builder=lambda d: (
                    f"No hay datos para el id_grupo {d['id_grupo']}"
                    + (f" en frecuencia {d['frecuencia']}" if d.get("frecuencia") else "")
                    + ". Prueba search_indicadores_bce para confirmar el id_grupo."
                ),
            )

        def to_text(data: dict) -> str:
            periodos = data.get("periodos") or []
            series = data.get("series") or []
            parts = [
                f"{data.get('grupo')} (id_grupo {data.get('id_grupo')})",
                f"Frecuencia: {data.get('frecuencia')}  ·  Unidad: {data.get('unidad')}",
                (
                    f"Período: {data.get('desde')} a {data.get('hasta')}"
                    f" ({len(periodos)} datos por serie)"
                ),
                "",
            ]
            if not series:
                parts.append("Sin series de datos.")
                return "\n".join(parts)
            for s in series:
                parts.append(f"{s.get('label')}" + (f" ({s['ruta']})" if s.get("ruta") else ""))
                valores = s.get("valores") or {}
                if valores and periodos:
                    primero, ultimo = periodos[0], periodos[-1]
                    parts.append(
                        f"   {primero}: {valores.get(primero)}  →  "
                        f"{ultimo}: {valores.get(ultimo)}"
                    )
                parts.append("")
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

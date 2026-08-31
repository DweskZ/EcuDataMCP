from mcp.server.fastmcp import FastMCP

from helpers import bce_indicadores_diarios_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_bce_indicadores_diarios_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_bce_indicadores_diarios(format: str = "text") -> str:
        """
        List BCE's family of daily/monthly "indicador" widgets published
        outside both BCEData and IEM (contenido.bce.fin.ec's Highcharts
        widget pages) — includes Riesgo País (EMBI) as a genuine daily
        series back to 2004, which BCEData only exposes as a monthly
        end-of-period aggregate.

        Also covers: Precio del Oro, Petróleo WTI, Índice Dow Jones, Tasa
        SOFR/LIBOR, Ecuador sovereign bond prices (all daily); Sistema de
        Pagos/Cobros Interbancarios, Sistema de Pagos en Línea, Cámara de
        Compensación de Cheques (monthly); Producción Petrolera Nacional
        (daily); inflación, desempleo, confianza del consumidor, PIB
        (monthly/quarterly/annual, likely duplicates BCEData).

        The catalog is discovered live from each file's own data, not
        hardcoded — a "codigo" only means one thing within its own
        "archivo", not across files. Follow up with
        get_bce_indicador_diario(archivo, codigo) for one series.

        Args:
            format: text | json
        """
        catalog = await bce_indicadores_diarios_client.list_indicadores()

        def to_text(data: list[dict]) -> str:
            parts = [f"Indicadores BCE (diarios/mensuales) — {len(data)} serie(s):", ""]
            for c in data:
                parts.append(
                    f"- [{c['archivo']} / {c['codigo']}] {c['indicador']} "
                    f"({c['periodicidad']}, {c['unidad']}): {c['fecha_desde']} → {c['fecha_hasta']} "
                    f"({c['n_datos']} datos)"
                )
            return "\n".join(parts)

        return render_output(catalog, format, text_builder=to_text)

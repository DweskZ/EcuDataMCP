import re
from datetime import date
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import bce_indicadores_diarios_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_fecha(nombre: str, valor: str) -> None:
    """The client compares dates as YYYY-MM-DD strings, so any other spelling
    ("01/01/2024") would silently select a wrong window instead of failing."""
    if not valor:
        return
    try:
        if not _ISO_DATE_RE.match(valor):
            raise ValueError(valor)
        date.fromisoformat(valor)
    except ValueError as e:
        raise ToolError(f"{nombre} debe tener formato YYYY-MM-DD") from e


def register_get_bce_indicador_diario_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Ver serie de un indicador diario del BCE",
        description=(
            "One BCE daily/monthly indicator (archivo and codigo from "
            "list_catalogo(fuente='bce_diarios')): the last ultimos_n points or a date "
            "range, capped at 366 rows."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_bce_indicador_diario(
        archivo: str,
        codigo: str,
        ultimos_n: int = 30,
        desde: str = "",
        hasta: str = "",
        format: Literal["text", "json"] = "text",
    ) -> CallToolResult:
        """
        Fetch one BCE daily/monthly indicator's time series (e.g. Riesgo
        País), bounded to a window — never the full series (some run
        7,000+ observations).

        Get archivo/codigo from list_catalogo(fuente='bce_diarios') first — a
        codigo only means one thing within its own archivo. Without
        desde/hasta, returns the most recent ultimos_n observations
        (capped at 366). With desde/hasta (YYYY-MM-DD, inclusive), returns
        that date range instead, also capped at 366 rows (most recent
        within the range if it's larger). The response always includes
        rango_completo (the series' true full date range and row count)
        so the window returned is never mistaken for the whole series.
        Each point in "datos" has "valor" (one number) for almost every
        indicator, except Inflación (datos_ipc.json), which has no single
        value — its points carry "valores": {"Mensual":..., "Anual":...,
        "Acumulada":...} instead.

        Args:
            archivo: A file name from list_catalogo(fuente='bce_diarios').
            codigo: A "Código Variable Dinámica" from that same archivo.
            ultimos_n: Most recent N observations when no date range is given.
            desde: Optional start date YYYY-MM-DD.
            hasta: Optional end date YYYY-MM-DD.
            format: text | json
        """
        _validate_fecha("desde", desde)
        _validate_fecha("hasta", hasta)
        try:
            result = await bce_indicadores_diarios_client.get_indicador_diario(
                archivo, codigo, ultimos_n=ultimos_n, desde=desde or None, hasta=hasta or None
            )
        except ValueError as e:
            raise ToolError(f"Error: {e}") from e
        except Exception as e:
            raise ToolError(f"Error al consultar el indicador diario del BCE: {e}") from e

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
            if data.get("truncado"):
                parts.append(
                    f"  (recortada a los últimos {len(datos)} de "
                    f"{data['observaciones_en_rango']} datos en el rango pedido; "
                    "acota desde/hasta para ver el resto)"
                )
            for d in datos:
                if "valor" in d:
                    parts.append(f"  {d['fecha']}: {d['valor']}")
                else:
                    valores = ", ".join(f"{k}={v}" for k, v in d["valores"].items())
                    parts.append(f"  {d['fecha']}: {valores}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

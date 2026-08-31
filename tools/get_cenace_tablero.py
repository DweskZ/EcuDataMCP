from mcp.server.fastmcp import FastMCP

from helpers import cenace_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_cenace_tablero_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_cenace_tablero(tablero: str, format: str = "text") -> str:
        """
        Fetch one tablero (tab) of CENACE's live grid-operations snapshot
        (Ecuador's national electricity operator) — generation mix and
        demand, always as-of-now.

        Tableros:
        - produccion_tiempo_real: current instant.
        - demanda_tiempo_real: current instant, plus a per-distributor
          (empresa eléctrica/CNEL) MW breakdown.
        - operativa_diaria: yesterday's full day total.
        - acumulada_mensual: month-to-date total (MWh).
        - acumulada_anual: year-to-date total (GWh).

        Each returns "resumen" (produccion total/exportación/importación/
        hidráulica/térmica/renovable no convencional, or the demand
        equivalent). There is no historical query here — CENACE's page
        has no date picker, only these 5 as-of-now views.

        Args:
            tablero: One of the 5 names above.
            format: text | json
        """
        try:
            result = await cenace_client.get_tablero(tablero)
        except ValueError as e:
            return render_output(
                {"error": str(e), "tablero": tablero},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        def to_text(data: dict) -> str:
            parts = [f"{data['titulo']} — {data['periodo']}", ""]
            for label, value in data["resumen"].items():
                parts.append(f"  {label}: {value:,}".replace(",", " "))
            distribuidoras = data.get("por_distribuidora_mw")
            if distribuidoras:
                parts.append("")
                parts.append("Por distribuidora (MW):")
                for name, mw in sorted(distribuidoras.items(), key=lambda kv: -kv[1]):
                    parts.append(f"  {name}: {mw:,}".replace(",", " "))
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

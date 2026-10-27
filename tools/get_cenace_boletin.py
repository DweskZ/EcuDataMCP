from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import cenace_boletin_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_cenace_boletin_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Leer el boletín mensual de transacciones de CENACE",
        description=(
            "CENACE monthly electricity-market bulletin (2019 onward): production "
            "by resource, demand by distributor, average prices, trade with "
            "Colombia and Peru. Empty mes lists the issues; mes=YYYY-MM returns "
            "its text by page."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_cenace_boletin(
        mes: str = "",
        anio: int | None = None,
        format: Literal["text", "json"] = "text",
    ) -> CallToolResult:
        """
        Read CENACE's "Boletín y Estadística Mensual de Transacciones
        Comerciales", the monthly report of Ecuador's electricity market
        (January 2019 onward, one issue a month, about a month behind).

        Each issue covers the month and year to date: production by resource
        (hydro, thermal by fuel, non-conventional renewables, imports),
        commercial demand by distributor (CNEL units and empresas
        eléctricas), self-generators, average energy prices in USD¢/kWh and
        the international transactions with Colombia and Peru (energy and
        value). None of this is in CKAN's `cenace` datasets.

        CENACE publishes the issues only as FlipHTML5 flipbooks; this tool
        reads the flipbook's text index, so tables come back as text rows
        ("CNEL GUAYAQUIL 3 036.06 39.1%", thousands separated by a space)
        rather than structured columns, and charts carry only their labels.
        Older issues (2019-2020) are shorter (6-9 pages) than recent ones
        (13).

        Args:
            mes: Empty to list the issues; YYYY-MM (e.g. 2026-07) or
                "ultimo" for one issue's text.
            anio: With an empty mes, list only that year's issues.
            format: text | json
        """
        try:
            if mes.strip():
                result = await cenace_boletin_client.get_boletin(mes)
            else:
                result = await cenace_boletin_client.list_boletines(anio)
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Error al consultar el boletín de CENACE: {e}") from e

        def to_text(data: dict) -> str:
            if "boletines" in data:
                parts = [
                    f"Boletines mensuales de CENACE — {data['total']} número(s):",
                    "",
                ]
                parts.extend(f"- {b['mes']}: {b['titulo']}" for b in data["boletines"])
                parts.extend(["", f"Fuente: {data['url_fuente']}"])
                return "\n".join(parts)
            parts = [data["titulo"], f"Flipbook: {data['url']}"]
            for p in data["paginas"]:
                parts.extend(
                    [
                        "",
                        f"--- Página {p['pagina']} de {data['total_paginas']} ---",
                        p["texto"],
                    ]
                )
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

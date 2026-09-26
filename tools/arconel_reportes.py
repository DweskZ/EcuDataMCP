from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import arconel_reportes_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

_TEXT_ROWS = 25


def register_list_arconel_reportes_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Listar reportes estadísticos de ARCONEL", annotations=READ_ONLY)
    @log_tool
    async def list_arconel_reportes(
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        List the report types available in ARCONEL's public statistics
        report builder (reportes.arconel.gob.ec — Ecuador's electricity
        regulator), grouped by section: per-parish data (meters, billing,
        Tarifa Dignidad subsidy), infrastructure (substations, lines,
        plants, meters, public lighting), transactions (energy balance,
        bought/sold/produced energy, losses, billing), and service-quality
        indicators. Also lists the available years (1998-current) and
        company groups. Use `get_arconel_reporte` to run one.

        Args:
            format: text | json
        """
        try:
            result = await arconel_reportes_client.list_arconel_reportes()
        except Exception as e:
            raise ToolError(f"Error al consultar el catálogo de ARCONEL: {e}") from e

        def to_text(data: dict) -> str:
            parts = ["ARCONEL — reportes estadísticos disponibles", ""]
            seccion = None
            for t in data["tipos"]:
                if t["seccion"] != seccion:
                    seccion = t["seccion"]
                    parts.append(f"[{seccion}]")
                parts.append(f"  - {t['tipo']}")
            anios = data["anios"]
            parts.append("")
            parts.append(f"Años: {anios[-1]}-{anios[0]}" if anios else "Años: ninguno")
            parts.append(f"Grupos: {', '.join(data['grupos'])}")
            parts.append(f"Fuente: {data['url_fuente']}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)


def register_get_arconel_reporte_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Consultar reporte estadístico de ARCONEL", annotations=READ_ONLY)
    @log_tool
    async def get_arconel_reporte(
        tipo: str,
        anio: int,
        grupo: Literal["todos", "cnel", "empresas_electricas"] = "todos",
        mes: int | None = None,
        max_paginas: int = 10,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Run one report from ARCONEL's public statistics builder
        (reportes.arconel.gob.ec) and return its rows, e.g. "Balance
        Energía" 2023 → monthly energy received, sold, and lost per
        distributor (CNEL units and Empresas Eléctricas), with technical
        and non-technical loss percentages.

        Slow by nature: ARCONEL renders the report server-side, page by
        page (~50 rows each, several seconds per page). A year of "Balance
        Energía" is 6 pages (~10-60 s); per-parish reports can run to many
        pages, so `max_paginas` caps the work and the result's `completo`
        says whether the whole report was read. Results are cached 24h.

        Args:
            tipo: Report name as listed by `list_arconel_reportes`
                (accent/case-insensitive), e.g. "Balance Energía",
                "Pérdidas", "Medidores Catastro".
            anio: Year, 1998-current.
            grupo: todos | cnel | empresas_electricas.
            mes: 1-12, only for report types with a month filter (e.g.
                per-parish reports); others already break down by month.
            max_paginas: Maximum pages to read (1-40, default 10).
            format: text | json (json returns every row).
        """
        try:
            result = await arconel_reportes_client.get_arconel_reporte(
                tipo=tipo, anio=anio, grupo=grupo, mes=mes, max_paginas=max_paginas
            )
        except arconel_reportes_client.ArconelError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Error al consultar el reporte de ARCONEL: {e}") from e

        def to_text(data: dict) -> str:
            periodo = f"{data['anio']}" + (
                f"-{data['mes']:02d}" if data.get("mes") else ""
            )
            estado = "completo" if data["completo"] else "INCOMPLETO (sube max_paginas)"
            parts = [
                (
                    f"ARCONEL — {data['tipo']} — {periodo} — grupo {data['grupo']}: "
                    f"{data['total_filas']} filas, {data['paginas_leidas']} de "
                    f"{data['paginas_total']} páginas ({estado})"
                ),
                "",
                "Columnas: " + " | ".join(data["columnas"]),
                "",
            ]
            for fila in data["filas"][:_TEXT_ROWS]:
                parts.append(
                    " | ".join("" if v is None else str(v) for v in fila.values())
                )
            if data["total_filas"] > _TEXT_ROWS:
                parts.append(
                    f"... y {data['total_filas'] - _TEXT_ROWS} filas más (usa format=json)"
                )
            parts.append("")
            parts.append(f"Fuente: {data['url_fuente']}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

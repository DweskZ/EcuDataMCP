from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import sut_powerbi_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY

_TEXT_ROW_CAP = 200


def register_query_sut_indicador_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Consultar datos de un indicador del SUT o la Judicatura",
        description="Live query of one SUT or Consejo de la Judicatura dashboard's data model (fuente): choose campos, optional equality filtros (plain columns only) and a row limite. Take the indicador from list_catalogo(fuente) and its valid campos from get_sut_indicador_schema.",
        annotations=READ_ONLY,
    )
    @log_tool
    async def query_sut_indicador(
        indicador: str,
        campos: list[str],
        filtros: dict[str, str] | None = None,
        limite: int = 500,
        fuente: Literal["sut", "judicatura"] = "sut",
        format: Literal["text", "json"] = "text",
    ) -> CallToolResult:
        """
        Run a live query against one SUT Power BI dashboard's underlying
        data model — any combination of its fields, e.g. month AND
        industry together for "contratos" (a real monthly time series
        since 2015 by CIIU industry, province, gender, contract status —
        none of this is in the ministerio-del-trabajo CKAN datasets,
        which are a single current-snapshot stock count with no time
        dimension).

        fuente="judicatura" queries the Consejo de la Judicatura dashboards
        (e.g. audiencias by year and province: campos "CUB EST_CUB_AUDIENCIAS.
        Periodo [Año]" and "CUB EST_CUB_AUDIENCIAS.Contador [suma]").

        Get valid campos from get_sut_indicador_schema(indicador) first —
        an unrecognized field name raises an error naming the tool to
        call instead of guessing. filtros only accepts plain-column
        fields (not "[medida]"/hierarchy-level fields) and matches exact
        text equality, e.g. {"public contratos.Estado contrato": "Vigente"}.

        Rows can run into the thousands for a wide breakdown (e.g. every
        month x every industry) — narrow with filtros or fewer campos
        rather than raising limite past what's actually needed; format
        "json" is exact but still subject to the same limite cap.

        Args:
            indicador: A key from list_catalogo(fuente=<fuente>).
            campos: Field labels exactly as returned by
                get_sut_indicador_schema.
            filtros: Optional {campo: valor} equality filters, plain
                columns only.
            limite: Row cap applied server-side by the query itself
                (clamped to 20000; the result carries truncado=true when
                the cap was reached).
            fuente: sut (default) | judicatura
            format: text | json
        """
        try:
            result = await sut_powerbi_client.query_indicador(
                indicador, campos, filtros=filtros, limite=limite, fuente=fuente
            )
        except ValueError as e:
            raise ToolError(str(e)) from e

        def to_text(data: dict) -> str:
            filas = data.get("filas") or []
            parts = [f"Indicador {data.get('fuente', 'sut')}: {data.get('nombre')}", f"{len(filas)} fila(s)", ""]
            if not filas:
                parts.append("Sin resultados para esta combinación de campos/filtros.")
                if data.get("aviso"):
                    parts.append(data["aviso"])
                return "\n".join(parts)
            shown = filas[:_TEXT_ROW_CAP]
            for row in shown:
                parts.append(" | ".join(f"{k}={v}" for k, v in row.items()))
            if len(filas) > _TEXT_ROW_CAP:
                parts.append(
                    f"... ({len(filas) - _TEXT_ROW_CAP} fila(s) más — usa format=\"json\" "
                    "o acota con filtros/campos para verlas todas)"
                )
            if data.get("truncado"):
                parts.append(
                    f"Resultado truncado al límite de {data.get('limite')} filas: "
                    "acota con filtros o menos campos."
                )
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

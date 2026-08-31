from mcp.server.fastmcp import FastMCP

from helpers import sut_powerbi_client
from helpers.format_out import render_output
from helpers.logging import log_tool

_TEXT_ROW_CAP = 200


def register_query_sut_indicador_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def query_sut_indicador(
        indicador: str,
        campos: list[str],
        filtros: dict[str, str] | None = None,
        limite: int = 500,
        format: str = "text",
    ) -> str:
        """
        Run a live query against one SUT Power BI dashboard's underlying
        data model — any combination of its fields, e.g. month AND
        industry together for "contratos" (a real monthly time series
        since 2015 by CIIU industry, province, gender, contract status —
        none of this is in the ministerio-del-trabajo CKAN datasets,
        which are a single current-snapshot stock count with no time
        dimension).

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
            indicador: A key from list_sut_indicadores.
            campos: Field labels exactly as returned by
                get_sut_indicador_schema.
            filtros: Optional {campo: valor} equality filters, plain
                columns only.
            limite: Row cap applied server-side by the query itself.
            format: text | json
        """
        try:
            result = await sut_powerbi_client.query_indicador(
                indicador, campos, filtros=filtros, limite=limite
            )
        except ValueError as e:
            return render_output(
                {"error": str(e), "indicador": indicador},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        def to_text(data: dict) -> str:
            filas = data.get("filas") or []
            parts = [f"Indicador SUT: {data.get('nombre')}", f"{len(filas)} fila(s)", ""]
            if not filas:
                parts.append("Sin resultados para esta combinación de campos/filtros.")
                return "\n".join(parts)
            shown = filas[:_TEXT_ROW_CAP]
            for row in shown:
                parts.append(" | ".join(f"{k}={v}" for k, v in row.items()))
            if len(filas) > _TEXT_ROW_CAP:
                parts.append(
                    f"... ({len(filas) - _TEXT_ROW_CAP} fila(s) más — usa format=\"json\" "
                    "o acota con filtros/campos para verlas todas)"
                )
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

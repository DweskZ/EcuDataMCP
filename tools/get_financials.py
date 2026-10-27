import logging
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import supercias_financials
from helpers.format_out import render_structured
from helpers.logging import MAIN_LOGGER_NAME, log_tool
from helpers.tool_meta import READ_ONLY

logger = logging.getLogger(MAIN_LOGGER_NAME)

_DISPLAY_FIELDS = (
    ("ingresos_ventas", "Ingresos por ventas"),
    ("activos", "Activos"),
    ("patrimonio", "Patrimonio"),
    ("utilidad_ejercicio", "Utilidad del ejercicio"),
    ("utilidad_neta", "Utilidad neta"),
    ("n_empleados", "Empleados"),
    ("liquidez_corriente", "Liquidez corriente"),
    ("roe", "ROE"),
    ("roa", "ROA"),
    ("end_patrimonial", "Endeudamiento patrimonial"),
)


def register_get_financials_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Ver historial financiero de una compañía",
        description=(
            "One company's Supercías financial history (fiscal years 2008 to "
            "the latest): revenue, assets, equity, profit, employees and ratios. "
            "Takes expediente or RUC; anio or desde/hasta narrow the years."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_financials(
        expediente_or_ruc: str,
        anio: int | None = None,
        desde: int | None = None,
        hasta: int | None = None,
        format: Literal["text", "json"] = "text",
    ) -> CallToolResult:
        """
        Get a company's financial history from Supercías balance-sheet filings.

        Returns revenue, assets, equity, profit, employee count, and financial
        ratios (liquidity, leverage, profitability) per fiscal year, most
        recent first. Covers every fiscal year Supercías publishes, 2008 to
        the latest (`metadatos.base_local.anios_disponibles` lists them; the
        latest may still be incomplete). Ratios start in 2018 and CIIU in
        2009; earlier years only have revenue, assets, equity, profit, income
        tax and employees. A year with no financial statement shows as such.
        Ratios Supercías could not calculate are empty (null), not 0. Each
        year with a CIIU sector also carries `cuartiles_sector`: p25, median
        and p75 of the main ratios across that sector's filings that year,
        computed from the ranking itself (Supercías' own sector means are
        dominated by a few extreme filings and are not used).
        margen_operacional, per_med_cobranza and per_med_pago have no
        consistent scale in the source; read them with caution.
        If a RUC maps to several companies, the error lists their expedientes.
        Complements get_compania_info, which has legal/registry data but no
        financials.

        Args:
            expediente_or_ruc: The company's Supercías "expediente" number
                (from search_companias/get_compania_info) or its 13-digit RUC.
            anio: Optional single fiscal year. A year not in the local build
                returns an error listing the available years.
            desde: Optional first fiscal year of a range (inclusive).
            hasta: Optional last fiscal year of a range (inclusive). Don't
                combine desde/hasta with anio.
            format: text | json
        """
        try:
            result = await supercias_financials.get_financials(
                expediente_or_ruc, anio, desde, hasta
            )
        except supercias_financials.FinancialsDbUnavailable as e:
            raise ToolError(str(e)) from e
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            logger.exception(
                "get_financials failed (expediente_or_ruc=%r)", expediente_or_ruc
            )
            raise ToolError(
                f"Error al consultar los financieros de Supercías: {e}"
            ) from e

        if result.get("error") == "ambiguous":
            candidatos = "; ".join(
                f"expediente {c['expediente']} ({c.get('nombre') or 'sin nombre'})"
                for c in result["candidatos"]
            )
            raise ToolError(
                f"El RUC '{expediente_or_ruc}' corresponde a varias compañías en "
                f"Supercías: {candidatos}. Vuelve a consultar con el expediente."
            )
        if result.get("error") == "not_found":
            raise ToolError(
                f"Error: no se encontró ninguna compañía con "
                f"'{expediente_or_ruc}'. Prueba search_companias primero."
            )

        result = supercias_financials.with_financials_metadata(result)

        def to_text(data: dict) -> str:
            years = data.get("years") or []
            header = data.get("nombre") or f"Expediente {data.get('expediente')}"
            parts = [f"Financieros: {header}"]
            parts.extend(supercias_financials.stale_warning_lines(data))
            if data.get("ruc"):
                parts.append(f"RUC: {data['ruc']}")
            parts.append(f"Expediente: {data.get('expediente')}")
            parts.append("")
            if not years:
                parts.append(
                    "Sin datos financieros de esta compañía en los años pedidos "
                    "(no aparece en el ranking de Supercías esos años)."
                )
                return "\n".join(parts)
            for y in years:
                parts.append(f"--- Año fiscal {y.get('anio')} ---")
                # Unranked rows (2008-2018 mostly) carry zeros, not figures.
                if y.get("id_estado_financiero") is None:
                    parts.append("  Sin estado financiero presentado ese año.")
                cuartiles = y.get("cuartiles_sector") or {}
                for key, label in _DISPLAY_FIELDS:
                    value = y.get(key)
                    if value is not None:
                        line = f"  {label}: {value}"
                        if key in cuartiles:
                            q = cuartiles[key]
                            line += (
                                f" (sector {y.get('ciiu_n1')}: p25 {q['p25']:.2f}"
                                f" · mediana {q['mediana']:.2f}"
                                f" · p75 {q['p75']:.2f}, n={q['n']})"
                            )
                        parts.append(line)
                parts.append("")
            return "\n".join(parts).rstrip()

        return render_structured(result, format, text_builder=to_text)

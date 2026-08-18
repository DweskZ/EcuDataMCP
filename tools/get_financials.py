import logging

from mcp.server.fastmcp import FastMCP

from helpers import supercias_financials
from helpers.format_out import render_output
from helpers.logging import MAIN_LOGGER_NAME, log_tool

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


def register_get_financials_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_financials(
        expediente_or_ruc: str, anio: int | None = None, format: str = "text"
    ) -> str:
        """
        Get a company's financial history from Supercías balance-sheet filings.

        Returns revenue, assets, equity, profit, employee count, and financial
        ratios (liquidity, leverage, profitability) per fiscal year. Covers
        only the last few fiscal years (whatever scripts/build_supercias_financials_db.py
        last cached), not the full history back to 2008. Complements
        get_compania_info, which has legal/registry data but no financials.

        Args:
            expediente_or_ruc: The company's Supercías "expediente" number
                (from search_companias/get_compania_info) or its 13-digit RUC.
            anio: Optional single fiscal year filter.
            format: text | json
        """
        try:
            result = await supercias_financials.get_financials(
                expediente_or_ruc, anio
            )
        except supercias_financials.FinancialsDbUnavailable as e:
            return render_output(
                {"error": str(e), "expediente_or_ruc": expediente_or_ruc},
                format,
                text_builder=lambda d: d["error"],
            )
        except Exception as e:
            logger.exception(
                "get_financials failed (expediente_or_ruc=%r)", expediente_or_ruc
            )
            return render_output(
                {"error": str(e), "expediente_or_ruc": expediente_or_ruc},
                format,
                text_builder=lambda d: (
                    f"Error al consultar los financieros de Supercías: {d['error']}"
                ),
            )

        if result.get("error") == "not_found":
            return render_output(
                result,
                format,
                text_builder=lambda d: (
                    f"Error: no se encontró ninguna compañía con "
                    f"'{d['expediente_or_ruc']}'. Prueba search_companias primero."
                ),
            )

        def to_text(data: dict) -> str:
            years = data.get("years") or []
            header = data.get("nombre") or f"Expediente {data.get('expediente')}"
            parts = [f"Financieros: {header}"]
            if data.get("ruc"):
                parts.append(f"RUC: {data['ruc']}")
            parts.append(f"Expediente: {data.get('expediente')}")
            parts.append("")
            if not years:
                parts.append(
                    "Sin datos financieros cacheados para esta compañía "
                    "(fuera del rango de años disponible, o sin filings)."
                )
                return "\n".join(parts)
            for y in years:
                parts.append(f"--- Año fiscal {y.get('anio')} ---")
                for key, label in _DISPLAY_FIELDS:
                    value = y.get(key)
                    if value is not None:
                        parts.append(f"  {label}: {value}")
                parts.append("")
            return "\n".join(parts).rstrip()

        return render_output(result, format, text_builder=to_text)

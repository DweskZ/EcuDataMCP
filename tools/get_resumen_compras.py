from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import sercop_client
from helpers.ecuador_time import today_ecuador
from helpers.env_config import get_base_url
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.result_types import ResultadoTabla
from helpers.sercop_client import SUMMARY_MAX_PAGES, SercopRateLimitError
from helpers.tool_meta import READ_ONLY


def _usd(value: float) -> str:
    return f"USD {value:,.2f}"


def register_get_resumen_compras_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Resumir las compras públicas de una institución (SERCOP)",
        description=(
            "Summarize one buyer's SERCOP procurement in a year: process count, "
            "total amount, by procedure type, by month and top suppliers. Reads up "
            "to 300 processes and says when the summary is partial."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_resumen_compras(
        comprador: str,
        year: int = 0,
        query: str = "",
        format: Literal["text", "json"] = "text",
    ) -> Annotated[CallToolResult, ResultadoTabla]:
        """
        Summarize the public procurement of one buyer (institution) in a year,
        from SERCOP's OCDS open data.

        Pages through the same search search_contratos uses, filtered by
        buyer, and totals what it reads: number of processes, total amount
        (the OCDS `amount`, awarded or estimated value) and budget, split by
        procedure type, by month and by supplier, plus first and last dates.
        `comprador` is a keyword, so several institutions can match ("agua"
        matches every water utility); each is summarized on its own, largest
        first, top 10.

        Limits: reads at most 300 processes (30 pages); past that the summary
        is marked `parcial` with `total_en_fuente`. Processes without an
        amount are counted but add nothing (`procesos_con_monto`). Supplier
        names are only present on some search rows. SERCOP rate-limits busy
        clients; a page that fails is listed in `paginas_fallidas`. For one
        process's full record use get_contrato_info(ocid).

        Args:
            comprador: Buyer/institution keyword, min 3 chars (e.g. "Municipio de Quito", "IESS").
            year: Year of the processes (2015-current). 0 = current year.
            query: Optional topic keyword (min 3 chars) to narrow the processes; empty uses the buyer keyword.
            format: text | json
        """
        comprador = (comprador or "").strip()
        if len(comprador) < 3:
            raise ToolError("Error: comprador debe tener al menos 3 caracteres.")
        query = (query or "").strip()
        if query and len(query) < 3:
            raise ToolError("Error: query debe tener al menos 3 caracteres o ir vacío.")
        year = year if year > 0 else today_ecuador().year
        if year < 2015:
            raise ToolError("Error: SERCOP publica datos OCDS desde 2015.")

        try:
            result = await sercop_client.summarize_buyer(comprador, year, query=query)
        except SercopRateLimitError as e:
            raise ToolError(f"SERCOP ocupado: {e}") from e
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Error al resumir las compras en SERCOP: {e}.") from e

        site = get_base_url("sercop_site").rstrip("/")
        payload = {
            **result,
            "source": "SERCOP — Datos Abiertos de Compras Públicas (OCDS)",
            "url_fuente": f"{site}/procedimientos",
            "nota": (
                "Montos según el campo amount de la búsqueda OCDS (valor adjudicado o "
                "estimado); los procesos sin monto se cuentan pero no suman."
            ),
        }

        def to_text(p: dict) -> str:
            parts = [
                f"Compras públicas (SERCOP) — comprador '{p['comprador']}' — {p['year']}",
                f"Procesos leídos: {p['procesos_leidos']} de {p['total_en_fuente']}"
                + (f" (parcial: máximo {SUMMARY_MAX_PAGES * 10})" if p["parcial"] else ""),
                (
                    f"Monto total: {_usd(p['monto_total'])} "
                    f"({p['procesos_con_monto']} procesos con monto)"
                ),
            ]
            if p["paginas_fallidas"]:
                parts.append(f"⚠ Páginas que fallaron: {p['paginas_fallidas']}")
            if not p["compradores"]:
                parts.append("\nNo se encontraron procesos para ese comprador y año.")
                return "\n".join(parts)
            for c in p["compradores"]:
                parts.append("")
                parts.append(f"■ {c['comprador']}")
                parts.append(
                    f"  {c['procesos']} procesos · {_usd(c['monto_total'])} · "
                    f"presupuesto {_usd(c['presupuesto_total'])} · "
                    f"{c['primera_fecha'] or '?'} a {c['ultima_fecha'] or '?'}"
                )
                for t in c["por_tipo"][:5]:
                    parts.append(f"  - {t['tipo']}: {t['procesos']} · {_usd(t['monto'])}")
                if c["proveedores"]:
                    top = ", ".join(
                        f"{s['proveedor']} ({_usd(s['monto'])})" for s in c["proveedores"][:3]
                    )
                    parts.append(f"  Proveedores principales: {top}")
            if p["otros_compradores"]:
                parts.append(f"\n… y {p['otros_compradores']} compradores más (ver format=json).")
            parts.append("\nTip: search_contratos lista los procesos; get_contrato_info(ocid) da el expediente.")
            return "\n".join(parts)

        return render_structured(payload, format, text_builder=to_text)

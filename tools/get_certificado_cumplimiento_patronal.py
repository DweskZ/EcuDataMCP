from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import iess_certificado_patronal_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_certificado_cumplimiento_patronal_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Verificar cumplimiento de obligaciones patronales (IESS)",
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_certificado_cumplimiento_patronal(
        identificacion: str, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        Check whether an employer (13-digit RUC) or individual (10-digit
        cédula) is current on Seguro Social (IESS) contributions, via the
        IESS's public "Certificado de Cumplimiento de Obligaciones
        Patronales" — no login required.

        Scope: this is a mora/no-mora compliance check, NOT an employee
        or affiliate headcount — the IESS itself does not publish that
        figure anywhere publicly (confirmed 2026-09-21). For the actual
        employee count, use get_financials/search_ranking's
        `n_empleados` field instead (self-reported to Supercías'
        Ranking, not this tool) — get_compania_info's basic registry
        doesn't carry it, but the Ranking dataset does.

        Args:
            identificacion: A 10-digit cédula or 13-digit RUC.
            format: text | json
        """
        try:
            result = await iess_certificado_patronal_client.get_certificado_cumplimiento_patronal(
                identificacion
            )
        except Exception as e:
            raise ToolError(
                f"Error al consultar el certificado de cumplimiento patronal del IESS: {e}"
            ) from e

        def to_text(data: dict) -> str:
            if not data.get("encontrado"):
                return (
                    f"IESS — Certificado de Cumplimiento Patronal: sin resultado para "
                    f"{data.get('identificacion_consultada')}.\n{data.get('motivo')}"
                )
            moroso = data.get("moroso")
            if moroso is None:
                estado = (
                    "NO DETERMINADO — no se pudo interpretar el texto del certificado; "
                    "revisa texto_completo (format=json)"
                )
            elif moroso:
                estado = "SÍ registra obligaciones en mora"
            else:
                estado = "NO registra obligaciones en mora"
            parts = [
                f"IESS — Certificado de Cumplimiento Patronal — {data.get('identificacion_consultada')}",
                "",
                f"Persona: {data.get('persona')}",
            ]
            if data.get("empresa"):
                parts.append(f"Empresa: {data.get('empresa')}")
            parts.append(f"Dirección: {data.get('direccion')}")
            parts.append(f"Estado: {estado}")
            parts.append(f"Emitido: {data.get('fecha_emision')} (válido {data.get('validez_dias')} días)")
            parts.append("")
            parts.append(data.get("nota_alcance", ""))
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

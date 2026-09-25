from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import supercias_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_auditor_info_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Ver información de un auditor externo", annotations=READ_ONLY)
    @log_tool
    async def get_auditor_info(
        identificacion: str, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        Get full registry details for an authorized external auditor by identificación (Superintendencia de Compañías).

        Returns authorization resolution number/date, nationality, address
        and contact details. Use search_auditores first if you don't have
        the exact identificación (RUC/cédula).

        Args:
            identificacion: The auditor's RUC or cédula
            format: text | json
        """
        try:
            auditor = await supercias_client.get_auditor_info(identificacion)
        except Exception as e:
            raise ToolError(
                f"Error al consultar el listado de auditores externos: {e}"
            ) from e

        if auditor is None:
            raise ToolError(
                f"Error: no se encontró ningún auditor externo con "
                f"identificación '{identificacion}'. Prueba "
                "search_auditores para buscar por nombre."
            )

        def to_text(a: dict) -> str:
            parts = [
                f"Auditor externo: {a.get('nombre')}",
                "",
                f"Identificación: {a.get('identificacion')}",
                f"RNAE: {a.get('rnae')}",
                f"Nacionalidad: {a.get('nacionalidad')}",
                f"Resolución: {a.get('numero_de_resolucion')} ({a.get('fecha_de_resolucion')})",
            ]
            ubicacion = "  ·  ".join(
                part for part in (a.get("provincia"), a.get("canton")) if part
            )
            if ubicacion:
                parts.append("")
                parts.append(f"Ubicación: {ubicacion}")
            if a.get("direccion"):
                parts.append(f"Dirección: {a['direccion']}")
            if a.get("telefono"):
                parts.append(f"Teléfono: {a['telefono']}")
            if a.get("correo_electronico"):
                parts.append(f"Correo: {a['correo_electronico']}")
            return "\n".join(parts)

        return render_structured(auditor, format, text_builder=to_text)

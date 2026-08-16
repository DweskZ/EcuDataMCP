from mcp.server.fastmcp import FastMCP

from helpers import supercias_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_auditor_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_auditor_info(identificacion: str, format: str = "text") -> str:
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
            return render_output(
                {"error": str(e), "identificacion": identificacion},
                format,
                text_builder=lambda d: (
                    f"Error al consultar el listado de auditores externos: {d['error']}"
                ),
            )

        if auditor is None:
            return render_output(
                {"error": "not_found", "identificacion": identificacion},
                format,
                text_builder=lambda d: (
                    f"Error: no se encontró ningún auditor externo con "
                    f"identificación '{d['identificacion']}'. Prueba "
                    "search_auditores para buscar por nombre."
                ),
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

        return render_output(auditor, format, text_builder=to_text)

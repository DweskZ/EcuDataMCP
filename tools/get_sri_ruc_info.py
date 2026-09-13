from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import sri_ruc_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_sri_ruc_info_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Consultar información pública de un RUC", annotations=READ_ONLY)
    @log_tool
    async def get_sri_ruc_info(
        ruc: str,
        include_establecimientos: bool = True,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Consultar la información pública de un contribuyente por RUC en el SRI.

        Devuelve razón social, estado, tipo, actividad económica, fechas de
        registro y establecimientos públicos registrados. No devuelve
        declaraciones ni montos tributarios individuales.

        Args:
            ruc: RUC ecuatoriano exacto de 13 dígitos
            include_establecimientos: incluir establecimientos registrados
            format: text | json
        """
        try:
            data = await sri_ruc_client.get_ruc_info(
                ruc, include_establecimientos=include_establecimientos
            )
        except Exception as exc:
            raise ToolError(
                f"Error al consultar la ficha pública del RUC en el SRI: {exc}"
            ) from exc

        if data is None:
            raise ToolError(
                f"No se encontró información pública para el RUC '{ruc}'."
            )

        def to_text(result: dict) -> str:
            labels = (
                ("razon_social", "Razón social"),
                ("ruc", "RUC"),
                ("nombre_comercial", "Nombre comercial"),
                ("estado", "Estado"),
                ("clase_contribuyente", "Clase de contribuyente"),
                ("tipo_contribuyente", "Tipo de contribuyente"),
                ("obligado_contabilidad", "Obligado a llevar contabilidad"),
                ("actividad_economica_principal", "Actividad económica principal"),
                ("fecha_inicio_actividades", "Inicio de actividades"),
                ("fecha_cese_actividades", "Cese de actividades"),
                ("fecha_reinicio_actividades", "Reinicio de actividades"),
                ("fecha_actualizacion", "Fecha de actualización"),
                ("categoria_mipymes", "Categoría MiPymes"),
            )
            parts = ["Información pública del RUC — SRI", ""]
            for key, label in labels:
                if result.get(key) is not None:
                    parts.append(f"{label}: {result[key]}")

            if "establecimientos" in result:
                parts.extend(["", "Establecimientos registrados:"])
                establishments = result["establecimientos"]
                if not establishments:
                    parts.append("- Ninguno")
                else:
                    for establishment in establishments:
                        parts.append(
                            f"- {establishment['numero']}: "
                            f"{establishment['nombre_comercial'] or 'Sin nombre comercial'}; "
                            f"{establishment['ubicacion']}; {establishment['estado']}"
                        )

            parts.extend(
                [
                    "",
                    (
                        "Alcance: la ficha es registral y pública; no incluye "
                        "declaraciones, ventas, retenciones ni pagos tributarios "
                        "individuales."
                    ),
                    f"Fuente: {result['url_fuente']}",
                ]
            )
            return "\n".join(parts)

        return render_structured(data, format, text_builder=to_text)

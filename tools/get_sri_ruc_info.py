from mcp.server.fastmcp import FastMCP

from helpers import sri_ruc_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_sri_ruc_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_sri_ruc_info(
        ruc: str, include_establecimientos: bool = True, format: str = "text"
    ) -> str:
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
            return render_output(
                {"error": str(exc), "ruc": ruc},
                format,
                text_builder=lambda d: (
                    f"Error al consultar la ficha pública del RUC en el SRI: "
                    f"{d['error']}"
                ),
            )

        if data is None:
            return render_output(
                {"error": "not_found", "ruc": ruc},
                format,
                text_builder=lambda d: (
                    f"No se encontró información pública para el RUC '{d['ruc']}'."
                ),
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

        return render_output(data, format, text_builder=to_text)

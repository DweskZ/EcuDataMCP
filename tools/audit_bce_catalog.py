import logging

from mcp.server.fastmcp import FastMCP

from helpers import bce_client
from helpers.format_out import render_output
from helpers.logging import MAIN_LOGGER_NAME, log_tool

logger = logging.getLogger(MAIN_LOGGER_NAME)


def register_audit_bce_catalog_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def audit_bce_catalog(
        incluir_grupos: bool = False,
        format: str = "text",
    ) -> str:
        """Audit the live BCEData catalogue and report its coverage.

        Fetches the catalogue tree and every indicator group's metadata. The
        report counts groups, series, sections and failed metadata requests.
        Set incluir_grupos=true to include the complete per-group inventory.
        Use get_indicador_bce for the actual values of a selected group.

        Args:
            incluir_grupos: Include every discovered group's metadata in the
                response. Defaults to false to keep mobile responses small.
            format: text | json
        """
        try:
            result = await bce_client.audit_catalog(
                incluir_grupos=incluir_grupos
            )
        except Exception as exc:
            logger.exception("audit_bce_catalog failed")
            return render_output(
                {"error": str(exc)},
                format,
                text_builder=lambda data: (
                    f"Error al auditar el catálogo BCEData: {data['error']}"
                ),
            )

        def to_text(data: dict) -> str:
            parts = [
                "Auditoría BCEData",
                f"Consulta: {data['consultado_en']}",
                (
                    f"Nodos del árbol: {data['total_nodos']} · "
                    f"grupos: {data['total_grupos']} · "
                    f"correctos: {data['grupos_exitosos']} · "
                    f"con error: {data['grupos_con_error']}"
                ),
                f"Series descubiertas: {data['total_series']}",
                "",
                "Grupos por sección:",
            ]
            for section, total in data["secciones"].items():
                parts.append(f"- {section}: {total}")
            if data["errores"]:
                parts.extend(["", "Errores:"])
                for error in data["errores"]:
                    parts.append(
                        f"- {error.get('id_grupo')}: {error.get('detalle')}"
                    )
            if data.get("grupos"):
                parts.extend(["", "Inventario por grupo:"])
                for group in data["grupos"]:
                    parts.append(
                        f"- {group['id_grupo']}: {group['descripcion']} "
                        f"({group['total_series']} series; "
                        f"{'OK' if group['bundle_ok'] else 'ERROR'})"
                    )
            parts.extend(
                [
                    "",
                    (
                        "La auditoría valida metadatos; usa get_indicador_bce "
                        "para recuperar los valores de un grupo."
                    ),
                ]
            )
            return "\n".join(parts)

        return render_output(result, format, text_builder=to_text)

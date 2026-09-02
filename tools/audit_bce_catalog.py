import logging

from mcp.server.fastmcp import FastMCP

from helpers import bce_client
from helpers.format_out import render_output
from helpers.logging import MAIN_LOGGER_NAME, log_tool
from helpers.response_contract import with_response_metadata

logger = logging.getLogger(MAIN_LOGGER_NAME)


def register_audit_bce_catalog_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def audit_bce_catalog(
        incluir_grupos: bool = False,
        guardar_snapshot: bool = False,
        comparar_anterior: bool = False,
        auditar_grid: bool = False,
        format: str = "text",
    ) -> str:
        """Audit the live BCEData catalogue and report its coverage.

        Fetches the catalogue tree and every indicator group's metadata. The
        report counts groups, series, sections and failed metadata requests.
        Set incluir_grupos=true to include the complete per-group inventory.
        Use get_indicador_bce for the actual values of a selected group.
        Set guardar_snapshot=true to persist the audit under
        BCE_CATALOG_SNAPSHOT_DIR (or data/bce_catalog_snapshots by default).
        Set comparar_anterior=true to compare the current catalog with the
        last complete saved audit.
        Set auditar_grid=true to probe one latest period for every discovered
        frequency/unit combination. The value audit is bounded and persisted
        separately when guardar_snapshot=true.

        Args:
            incluir_grupos: Include every discovered group's metadata in the
                response. Defaults to false to keep mobile responses small.
            format: text | json
        """
        try:
            result = await bce_client.audit_catalog(
                incluir_grupos=incluir_grupos,
                guardar_snapshot=guardar_snapshot,
                comparar_anterior=comparar_anterior,
                auditar_grid=auditar_grid,
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
            grid_audit = data.get("auditoria_grid")
            if grid_audit:
                parts.extend(
                    [
                        "",
                        "Comprobación acotada de valores /grid:",
                        (
                            f"- consultadas: {grid_audit['combinaciones_consultadas']} / "
                            f"{grid_audit['total_combinaciones']}"
                        ),
                        f"- correctas: {grid_audit['combinaciones_exitosas']}",
                        f"- con error: {grid_audit['combinaciones_con_error']}",
                    ]
                )
                if grid_audit.get("archivo_guardado"):
                    parts.append(
                        f"- reporte de valores guardado: {grid_audit['archivo_guardado']['archivo']}"
                    )
            if data.get("grupos"):
                parts.extend(["", "Inventario por grupo:"])
                for group in data["grupos"]:
                    parts.append(
                        f"- {group['id_grupo']}: {group['descripcion']} "
                        f"({group['total_series']} series; "
                        f"{'OK' if group['bundle_ok'] else 'ERROR'})"
                    )
            comparison = data.get("comparacion")
            if comparison:
                parts.extend(["", "Cambios frente al último snapshot completo:"])
                if not comparison.get("disponible"):
                    parts.append(f"- {comparison['mensaje']}")
                else:
                    parts.extend(
                        [
                            f"- grupos nuevos: {len(comparison['grupos_nuevos'])}",
                            f"- grupos retirados: {len(comparison['grupos_retirados'])}",
                            f"- grupos modificados: {len(comparison['grupos_modificados'])}",
                        ]
                    )
            if data.get("snapshot"):
                snapshot = data["snapshot"]
                parts.extend(
                    [
                        "",
                        f"Snapshot guardado: {snapshot['archivo']}",
                        f"Snapshot completo: {'sí' if snapshot['completo'] else 'no'}",
                    ]
                )
            parts.extend(
                [
                    "",
                    (
                        "La auditoría de valores prueba un solo período reciente; "
                        "usa get_indicador_bce para recuperar series completas."
                    ),
                ]
            )
            return "\n".join(parts)

        result = with_response_metadata(
            result,
            source=result["source"],
            source_url=result["url_fuente"],
            freshness="auditoria_en_vivo",
            schema_name="bcedata_auditoria_catalogo_v1",
            schema_fields=[
                "total_grupos", "total_series", "errores", "revision_fuente",
                "auditoria_grid", "comparacion",
            ],
            consulted_at=result["consultado_en"],
        )
        return render_output(result, format, text_builder=to_text)

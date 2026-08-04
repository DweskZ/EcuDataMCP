from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.format_out import render_output
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool


def register_get_regulacion_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_regulacion_info(regulacion_id: str, format: str = "text") -> str:
        """
        Get detailed information about a regulation published on gob.ec.

        Returns type, Registro Oficial reference, description and PDF/archivo URL
        when available. Get the regulacion_id from search_regulaciones.

        Args:
            regulacion_id: Regulation ID (e.g. "5051")
            format: text | json
        """
        try:
            reg = await gobec_client.get_regulacion(regulacion_id)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al obtener regulación: {d['error']}",
            )

        if not reg:
            return render_output(
                {"error": "not_found", "regulacion_id": regulacion_id},
                format,
                text_builder=lambda d: (
                    f"No se encontró la regulación con ID '{d['regulacion_id']}'."
                ),
            )

        payload = {
            "regulacion_id": reg.get("regulacion_id", regulacion_id),
            "regulacion": _clean_html(reg.get("regulacion", "")).strip('"').strip(),
            "tipo": reg.get("tipo"),
            "institucion_emisora": reg.get("institucion_emisora"),
            "registro_oficial_numero": reg.get("registro_oficial_numero"),
            "registro_oficial_fecha": reg.get("registro_oficial_fecha"),
            "suscripcion": reg.get("suscripcion"),
            "url": reg.get("url"),
            "archivo": reg.get("archivo"),
            "descripcion": _clean_html(reg.get("descripcion", "")),
        }

        def to_text(data: dict) -> str:
            parts = [
                f"Regulación: {data.get('regulacion') or 'Sin título'}",
                f"ID: {data.get('regulacion_id')}",
            ]
            for label, key in (
                ("Tipo", "tipo"),
                ("Institución emisora", "institucion_emisora"),
                ("Registro Oficial", "registro_oficial_numero"),
                ("Fecha R.O.", "registro_oficial_fecha"),
                ("Suscripción", "suscripcion"),
                ("URL", "url"),
                ("Archivo PDF", "archivo"),
            ):
                if data.get(key):
                    parts.append(f"{label}: {data[key]}")
            if data.get("descripcion"):
                parts.append("")
                parts.append(f"Descripción:\n{data['descripcion']}")
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

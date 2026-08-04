from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.format_out import render_output
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool


def register_get_institucion_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_institucion_info(
        institucion_id: str, format: str = "text"
    ) -> str:
        """
        Get detailed information about a public institution registered on gob.ec.

        Returns name, acronym, sector, description, website and portal URL.
        Get the institucion_id from list_instituciones.

        Common IDs: SRI=8, IESS=5, Registro Civil=23, ANT=62, Cancillería=16.

        Args:
            institucion_id: Institution ID (e.g. "8")
            format: text | json
        """
        try:
            inst = await gobec_client.get_institucion(institucion_id)
        except Exception as e:
            return render_output(
                {"error": str(e), "institucion_id": institucion_id},
                format,
                text_builder=lambda d: f"Error al obtener institución: {d['error']}",
            )

        if not inst:
            return render_output(
                {"error": "not_found", "institucion_id": institucion_id},
                format,
                text_builder=lambda d: (
                    f"No se encontró la institución con ID '{d['institucion_id']}'."
                ),
            )

        nombre = inst.get("institucion") or inst.get("nombre") or "Desconocida"
        siglas = inst.get("siglas", "")
        desc = _clean_html(inst.get("descripcion", ""))
        payload = {
            "institucion_id": inst.get("institucion_id", institucion_id),
            "nombre": nombre,
            "siglas": siglas or None,
            "sector": inst.get("sector"),
            "website": inst.get("website"),
            "url": inst.get("url"),
            "email": inst.get("email"),
            "telefono": inst.get("telefono"),
            "descripcion": desc or None,
        }

        def to_text(data: dict) -> str:
            title = (
                f"{data['nombre']} ({data['siglas']})"
                if data.get("siglas")
                else data["nombre"]
            )
            parts = [
                f"Institución: {title}",
                f"ID: {data.get('institucion_id', institucion_id)}",
            ]
            if data.get("sector"):
                parts.append(f"Sector: {data['sector']}")
            if data.get("website"):
                parts.append(f"Web: {data['website']}")
            if data.get("url"):
                parts.append(f"Portal gob.ec: {data['url']}")
            if data.get("email"):
                parts.append(f"Email: {data['email']}")
            if data.get("telefono"):
                parts.append(f"Teléfono: {data['telefono']}")
            if data.get("descripcion"):
                parts.append("")
                parts.append(f"Descripción: {str(data['descripcion'])[:1000]}")
            parts.append("")
            parts.append(
                f"Tip: Usa search_tramites(institution_id='{institucion_id}') "
                "para ver sus trámites."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import gobec_client
from helpers.format_out import render_structured
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_institucion_info_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Ver detalle de una institución pública", annotations=READ_ONLY)
    @log_tool
    async def get_institucion_info(
        institucion_id: str, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
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
            raise ToolError(f"Error al obtener institución: {e}") from e

        if not inst:
            raise ToolError(f"No se encontró la institución con ID '{institucion_id}'.")

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

        return render_structured(payload, format, text_builder=to_text)

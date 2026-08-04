from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool


def register_get_regulacion_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_regulacion_info(regulacion_id: str) -> str:
        """
        Get detailed information about a regulation published on gob.ec.

        Returns type, Registro Oficial reference, description and PDF/archivo URL
        when available. Get the regulacion_id from search_regulaciones.

        Args:
            regulacion_id: Regulation ID (e.g. "5051")
        """
        try:
            reg = await gobec_client.get_regulacion(regulacion_id)
        except Exception as e:
            return f"Error al obtener regulación: {e}"

        if not reg:
            return f"No se encontró la regulación con ID '{regulacion_id}'."

        title = _clean_html(reg.get("regulacion", "Sin título")).strip('"').strip()
        parts = [
            f"Regulación: {title}",
            f"ID: {reg.get('regulacion_id', regulacion_id)}",
        ]
        if reg.get("tipo"):
            parts.append(f"Tipo: {reg['tipo']}")
        if reg.get("institucion_emisora"):
            parts.append(f"Institución emisora: {reg['institucion_emisora']}")
        if reg.get("registro_oficial_numero"):
            parts.append(f"Registro Oficial: {reg['registro_oficial_numero']}")
        if reg.get("registro_oficial_fecha"):
            parts.append(f"Fecha R.O.: {reg['registro_oficial_fecha']}")
        if reg.get("suscripcion"):
            parts.append(f"Suscripción: {reg['suscripcion']}")
        if reg.get("url"):
            parts.append(f"URL: {reg['url']}")
        if reg.get("archivo"):
            parts.append(f"Archivo PDF: {reg['archivo']}")

        desc = _clean_html(reg.get("descripcion", ""))
        if desc:
            parts.append("")
            parts.append(f"Descripción:\n{desc}")

        return "\n".join(parts)

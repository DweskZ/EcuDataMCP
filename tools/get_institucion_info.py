from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool


def register_get_institucion_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_institucion_info(institucion_id: str) -> str:
        """
        Get detailed information about a public institution registered on gob.ec.

        Returns name, acronym, sector, description, website and portal URL.
        Get the institucion_id from list_instituciones.

        Common IDs: SRI=8, IESS=5, Registro Civil=23, ANT=62, Cancillería=16.

        Args:
            institucion_id: Institution ID (e.g. "8")
        """
        try:
            inst = await gobec_client.get_institucion(institucion_id)
        except Exception as e:
            return f"Error al obtener institución: {e}"

        if not inst:
            return f"No se encontró la institución con ID '{institucion_id}'."

        nombre = inst.get("institucion") or inst.get("nombre") or "Desconocida"
        siglas = inst.get("siglas", "")
        title = f"{nombre} ({siglas})" if siglas else nombre

        parts = [f"Institución: {title}", f"ID: {inst.get('institucion_id', institucion_id)}"]

        if inst.get("sector"):
            parts.append(f"Sector: {inst['sector']}")
        if inst.get("website"):
            parts.append(f"Web: {inst['website']}")
        if inst.get("url"):
            parts.append(f"Portal gob.ec: {inst['url']}")
        if inst.get("email"):
            parts.append(f"Email: {inst['email']}")
        if inst.get("telefono"):
            parts.append(f"Teléfono: {inst['telefono']}")

        desc = _clean_html(inst.get("descripcion", ""))
        if desc:
            parts.append("")
            parts.append(f"Descripción: {desc[:1000]}")

        parts.append("")
        parts.append(
            f"Tip: Usa search_tramites(institution_id='{institucion_id}') "
            "para ver sus trámites."
        )
        return "\n".join(parts)

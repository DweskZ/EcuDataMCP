from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool


def register_get_tramite_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_tramite_info(tramite_id: str) -> str:
        """
        Get detailed information about a specific government procedure (trámite).

        Returns the procedure name, description, requirements, beneficiaries,
        cost, and the institution responsible. Get the tramite_id from search_tramites.

        Args:
            tramite_id: The procedure ID (e.g. "18009")
        """
        try:
            t = await gobec_client.get_tramite(tramite_id)
        except Exception as e:
            return f"Error al obtener trámite: {e}"

        if not t:
            return f"No se encontró el trámite con ID '{tramite_id}'."

        parts = [f"Trámite: {t.get('nombre', 'Desconocido')}", ""]

        if t.get("tramite_id"):
            parts.append(f"ID: {t['tramite_id']}")
        if t.get("codigo"):
            parts.append(f"Código: {t['codigo']}")
        if t.get("url"):
            parts.append(f"URL: {t['url']}")

        if t.get("institucion_id"):
            parts.append(f"Institución ID: {t['institucion_id']}")

        desc = _clean_html(t.get("descripcion", ""))
        if desc:
            parts.append("")
            parts.append(f"Descripción: {desc}")

        beneficiarios = _clean_html(t.get("beneficiarios", ""))
        if beneficiarios:
            parts.append("")
            parts.append(f"Beneficiarios: {beneficiarios}")

        requisitos = _clean_html(t.get("requisitos_obligatorios", ""))
        if requisitos:
            parts.append("")
            parts.append(f"Requisitos obligatorios:\n{requisitos}")

        requisitos_opt = _clean_html(t.get("requisitos_opcionales", ""))
        if requisitos_opt:
            parts.append("")
            parts.append(f"Requisitos opcionales:\n{requisitos_opt}")

        procedimiento = _clean_html(t.get("procedimiento", ""))
        if procedimiento:
            parts.append("")
            parts.append(f"Procedimiento:\n{procedimiento}")

        costo = _clean_html(t.get("costo", ""))
        if costo:
            parts.append("")
            parts.append(f"Costo: {costo}")

        tiempo = _clean_html(t.get("tiempo_estimado", t.get("tiempo", "")))
        if tiempo:
            parts.append(f"Tiempo estimado: {tiempo}")

        canales = _clean_html(t.get("canales_atencion", ""))
        if canales:
            parts.append("")
            parts.append(f"Canales de atención: {canales}")

        if t.get("imagen_url"):
            parts.append("")
            parts.append(f"Imagen: {t['imagen_url']}")

        # Linked regulations that underpin the procedure
        try:
            regs = await gobec_client.get_tramite_regulaciones(tramite_id)
        except Exception:
            regs = []
        if regs:
            parts.append("")
            parts.append(f"Regulaciones relacionadas ({len(regs)}):")
            for i, reg in enumerate(regs[:8], 1):
                title = _clean_html(
                    reg.get("regulacion") or reg.get("nombre") or "Regulación"
                ).strip('"')
                rid = reg.get("regulacion_id", "?")
                parts.append(f"{i}. {title} (ID: {rid})")
                if reg.get("registro_oficial_numero"):
                    parts.append(f"   R.O.: {reg['registro_oficial_numero']}")
            parts.append(
                "Tip: Usa get_regulacion_info(regulacion_id='...') para el detalle/PDF."
            )

        return "\n".join(parts)

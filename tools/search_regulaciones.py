from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool


def register_search_regulaciones_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_regulaciones(query: str = "", page: int = 1) -> str:
        """
        Search or list regulations published on Ecuador's gob.ec portal.

        Includes agreements, regulations and related norms with Registro Oficial
        references when available. With a query, scans several pages client-side
        (the API has no native search). Without a query, returns a paginated list.

        Args:
            query: Keywords (e.g. "datos personales", "tránsito", "LOTAIP")
            page: Page number when query is empty (1-based)
        """
        try:
            if query.strip():
                regs = await gobec_client.find_regulaciones(query.strip(), max_pages=6)
            else:
                api_page = max(page - 1, 0)
                regs = await gobec_client.list_regulaciones(page=api_page)
        except Exception as e:
            return f"Error al buscar regulaciones: {e}"

        if not regs:
            msg = "No se encontraron regulaciones"
            if query:
                msg += f" para '{query}'"
            return msg + "."

        parts = []
        if query.strip():
            parts.append(f"Regulaciones que coinciden con '{query}':")
            parts.append(f"Encontradas: {len(regs)} (máx. páginas escaneadas)\n")
        else:
            parts.append(f"Regulaciones en gob.ec (página {page}):")
            parts.append(f"Mostrando {min(len(regs), 20)} resultados\n")

        for i, reg in enumerate(regs[:20], 1):
            title = _clean_html(reg.get("regulacion", "Sin título")).strip('"').strip()
            parts.append(f"{i}. {title}")
            parts.append(f"   ID: {reg.get('regulacion_id', '?')}")
            if reg.get("tipo"):
                parts.append(f"   Tipo: {reg['tipo']}")
            if reg.get("registro_oficial_numero"):
                parts.append(
                    f"   Registro Oficial: {reg['registro_oficial_numero']}"
                    + (
                        f" ({reg['registro_oficial_fecha']})"
                        if reg.get("registro_oficial_fecha")
                        else ""
                    )
                )
            desc = _clean_html(reg.get("descripcion", ""))
            if desc:
                parts.append(f"   Descripción: {desc[:220]}")
            if reg.get("url"):
                parts.append(f"   URL: {reg['url']}")
            parts.append("")

        if len(regs) > 20:
            parts.append(f"... y {len(regs) - 20} más.")

        parts.append(
            "Tip: Usa get_regulacion_info(regulacion_id='...') para el detalle y el PDF."
        )
        return "\n".join(parts)

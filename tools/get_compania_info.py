from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import supercias_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_compania_info_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Ver información registral de una compañía", annotations=READ_ONLY)
    @log_tool
    async def get_compania_info(
        ruc: str, format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        Get full registry details for a company by RUC (Superintendencia de Compañías).

        Returns legal status, incorporation date, legal representative,
        registered capital, economic activity (CIIU), address and last
        balance-sheet year. Use search_companias first if you don't have the
        exact RUC.

        Args:
            ruc: The company's 13-digit RUC
            format: text | json
        """
        try:
            compania = await supercias_client.get_compania_by_ruc(ruc)
        except Exception as e:
            raise ToolError(
                f"Error al consultar el directorio de Supercías: {e}"
            ) from e

        if compania is None:
            raise ToolError(
                f"Error: no se encontró ninguna compañía con RUC '{ruc}'. "
                "Prueba search_companias para buscar por nombre."
            )

        def to_text(c: dict) -> str:
            direccion = ", ".join(
                part
                for part in (
                    " ".join(filter(None, [c.get("calle"), c.get("numero")])),
                    c.get("interseccion"),
                    c.get("barrio"),
                    c.get("ciudad"),
                    c.get("canton"),
                    c.get("provincia"),
                )
                if part
            )
            parts = [
                f"Compañía: {c.get('nombre')}",
                "",
                f"RUC: {c.get('ruc')}",
                f"Expediente: {c.get('expediente')}",
                f"Situación legal: {c.get('situacion_legal')}",
                f"Tipo: {c.get('tipo')}",
                f"Fecha de constitución: {c.get('fecha_constitucion')}",
            ]
            if direccion:
                parts.append("")
                parts.append(f"Dirección: {direccion}")
            if c.get("telefono"):
                parts.append(f"Teléfono: {c['telefono']}")
            parts.append("")
            parts.append(f"Representante: {c.get('representante')} ({c.get('cargo')})")
            parts.append(f"Capital suscrito: {c.get('capital_suscrito')}")
            parts.append(f"CIIU: {c.get('ciiu_nivel_1')} / {c.get('ciiu_nivel_6')}")
            if c.get("ultimo_balance"):
                parts.append(f"Último año de balance presentado: {c['ultimo_balance']}")
            return "\n".join(parts)

        return render_structured(compania, format, text_builder=to_text)

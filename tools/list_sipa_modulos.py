from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from helpers import sipa_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_list_sipa_modulos_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Listar módulos de estadísticas SIPA", annotations=READ_ONLY)
    @log_tool
    async def list_sipa_modulos(format: Literal["text", "json"] = "text") -> dict[str, Any]:
        """
        List SIPA's statistics-download modules (sipa.agricultura.gob.ec).

        SIPA (Sistema de Información Pública Agropecuaria) is the Ministry
        of Agriculture, Livestock and Fisheries' statistics portal —
        distinct from MPCEIP (industry/trade). It publishes real Excel
        files with agropecuario price, trade, credit, production, and
        census series back to the early 2000s, organized into four
        modules: económico, productivo, social, and censos y registros
        administrativos.

        Follow up with get_sipa_modulo_archivos(modulo) for one module's
        file listing.

        Args:
            format: text | json
        """
        modulos = sipa_client.list_modulos()
        payload = {"total": len(modulos), "modulos": modulos}

        def to_text(data: dict) -> str:
            rows = data["modulos"]
            parts = [f"Módulos de estadísticas SIPA — {len(rows)} módulo(s):", ""]
            for m in rows:
                parts.append(f"- {m['modulo']}: {m['nombre']}")
                parts.append(f"  {m['url']}")
            return "\n".join(parts)

        return render_structured(payload, format, text_builder=to_text)

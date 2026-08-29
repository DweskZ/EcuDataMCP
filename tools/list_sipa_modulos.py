from mcp.server.fastmcp import FastMCP

from helpers import sipa_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_sipa_modulos_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_sipa_modulos(format: str = "text") -> str:
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

        def to_text(data: list[dict]) -> str:
            parts = [f"Módulos de estadísticas SIPA — {len(data)} módulo(s):", ""]
            for m in data:
                parts.append(f"- {m['modulo']}: {m['nombre']}")
                parts.append(f"  {m['url']}")
            return "\n".join(parts)

        return render_output(modulos, format, text_builder=to_text)

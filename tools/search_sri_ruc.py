from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import sri_ruc_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_search_sri_ruc_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar contribuyentes por razón social",
        description=(
            "Find SRI taxpayers by partial razón social or trade name (min 4 "
            "characters) when the RUC is unknown. SRI caps results at 100."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def search_sri_ruc(
        razon_social: str,
        max_resultados: int = 25,
        format: Literal["text", "json"] = "text",
    ) -> CallToolResult:
        """
        Buscar contribuyentes en el RUC del SRI por razón social o nombre
        comercial (texto parcial), sin necesitar el RUC exacto de antemano.

        Complementa get_sri_ruc_info (que requiere el RUC exacto) para el
        caso "conozco el nombre de la empresa, no su RUC". Cada resultado
        incluye estado, tipo de contribuyente, régimen, actividad económica,
        representantes legales, y si es agente de retención/contribuyente
        especial/fantasma — no declaraciones ni montos tributarios
        individuales.

        El SRI limita esta búsqueda a 100 coincidencias por consulta; si
        total_reportado sale en 100, puede haber más contribuyentes de los
        que realmente se están devolviendo — usa un texto más específico
        para acotar.

        Args:
            razon_social: Text to search (min 4 characters), e.g. "BANANERA"
            max_resultados: How many results to return with full detail (max 100)
            format: text | json
        """
        try:
            result = await sri_ruc_client.search_by_razon_social(
                razon_social, max_resultados=max_resultados
            )
        except ValueError as e:
            raise ToolError(f"Error: {e}") from e
        except Exception as e:
            raise ToolError(f"Error al consultar el RUC en el SRI: {e}") from e

        def to_text(data: dict) -> str:
            parts = [
                f"Búsqueda RUC por razón social: \"{data['razon_social_buscada']}\"",
                f"Total reportado por el SRI: {data['total_reportado']}",
                "",
            ]
            if data["nota"]:
                parts.append(f"Nota: {data['nota']}")
                parts.append("")
            resultados = data["resultados"]
            if not resultados:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            parts.append(f"Resultados devueltos ({len(resultados)}):")
            for r in resultados:
                parts.append(f"- {r['ruc']}: {r['razon_social']} ({r['estado']}, {r['tipo_contribuyente']})")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

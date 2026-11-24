from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import anda_materiales
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.result_types import ResultadoArchivos
from helpers.tool_meta import READ_ONLY


def _text(data: dict) -> str:
    lines = [f"Materiales ANDA {data['id']} ({data['total']}):", data["url_fuente"]]
    for item in data["archivos"]:
        detail = ", ".join(x for x in (item.get("formato"), item.get("tamano")) if x)
        lines.append(f"- {item['nombre']}{f' [{detail}]' if detail else ''}: {item['url']}")
    lines.append(data["nota"])
    return "\n".join(lines)


def register_get_anda_materiales_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Listar materiales relacionados de ANDA",
        description=(
            "List downloadable related materials for one numeric INEC ANDA catalog ID, "
            "including aggregate-only studies such as IPC and canasta. Returns links, "
            "not parsed data. Discover the study with search_anda first."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_anda_materiales(
        id: str, format: Literal["text", "json"] = "text"
    ) -> Annotated[CallToolResult, ResultadoArchivos]:
        """List related-material download links for a numeric ANDA catalog ID.

        Aggregate-only studies can contain historical workbooks even when they
        have no microdata. Each link carries the file's own name (e.g. "1. Serie
        Historica del IPC.zip"), its format and size; see the catalog entry for
        workbook descriptions and periods. Download access does not imply
        statistical comparability.

        Args:
            id: Numeric ANDA catalog id from search_anda (its "id" field), e.g. "809"
            format: text | json
        """
        try:
            result = await anda_materiales.get_related_materials(id)
        except Exception as exc:
            raise ToolError(f"Error al consultar materiales de ANDA: {exc}") from exc
        return render_structured(result, format, text_builder=_text)

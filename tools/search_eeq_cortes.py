from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import eeq_cortes_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_search_eeq_cortes_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar cortes de luz programados (EEQ, Quito)", annotations=READ_ONLY
    )
    @log_tool
    async def search_eeq_cortes(
        query: str = "", format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        List Empresa Eléctrica Quito's (EEQ — Quito and its concession
        area) archive of scheduled power-cut PDFs ("Programación cortes
        del servicio de energía eléctrica") from the 2023 and 2024
        national blackout crises. Each PDF lists, per time block, the
        substations and the streets/neighbourhoods without power.

        Regional, not national — EEQ's concession area only. Mid-October
        to December 2024 is enumerated live from EEQ's own site search;
        earlier files (Oct-Nov 2023, April/June 2024, Sep-early Oct 2024)
        come from a fixed list recovered via search-engine indexing, so
        that period may have gaps. Each entry's `origen` says which.
        Read a file's contents with `read_pdf` on its `url`.

        Args:
            query: Free text matched (accent-insensitive) against the
                periodo, fecha (YYYY-MM-DD), or slug — e.g. "noviembre",
                "2023", "2024-10". Empty returns all files.
            format: text | json
        """
        try:
            result = await eeq_cortes_client.search_eeq_cortes(query=query)
        except Exception as e:
            raise ToolError(
                f"Error al consultar el archivo de cortes de EEQ: {e}"
            ) from e

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"EEQ (Quito) — Cortes de luz programados — {data['total']} resultado(s) de "
                    f"{data['total_en_archivo']} archivos"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, a in enumerate(archivos, 1):
                parts.append(
                    f"{i}. {a['periodo']} [{a.get('fecha') or 'fecha desconocida'}]"
                )
                parts.append(f"   {a['url']}")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

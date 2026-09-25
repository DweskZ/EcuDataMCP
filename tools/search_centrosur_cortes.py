from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import centrosur_cortes_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_search_centrosur_cortes_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Buscar cortes de luz programados (Centrosur)", annotations=READ_ONLY)
    @log_tool
    async def search_centrosur_cortes(
        query: str = "", format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        List Centrosur's (Empresa Eléctrica Regional Centro Sur — Azuay,
        Cañar, Morona Santiago) archive of scheduled power-cut PDFs
        ("Programación de cortes del servicio de energía eléctrica"),
        including the 2024 national hydrological-crisis blackouts
        (estiaje, Sep-Dec 2024) as well as ordinary maintenance cuts.

        Regional, not national — only Centrosur's concession area. This
        is the only distributor in the project with a confirmed,
        unauthenticated enumeration mechanism (WordPress's own Media
        Library REST API); EEQ's equivalent archive is only discoverable
        via search-engine indexing (no public API), and CNEL has no
        recoverable archive at all. A separate Centrosur folder
        (`CortesEstiaje/`) holds additional 2024 PDFs uploaded outside
        the media library — not covered here, no known way to enumerate
        it programmatically.

        Args:
            query: Free text matched (accent-insensitive) against the
                file's titulo, anio, mes, or URL. Empty returns all files.
            format: text | json
        """
        try:
            result = await centrosur_cortes_client.search_centrosur_cortes(query=query)
        except Exception as e:
            raise ToolError(f"Error al consultar el archivo de cortes de Centrosur: {e}") from e

        def to_text(data: dict) -> str:
            archivos = data.get("archivos") or []
            parts = [
                (
                    f"Centrosur — Cortes de luz programados — {data['total']} resultado(s) de "
                    f"{data['total_en_archivo']} archivos"
                ),
                "",
            ]
            if not archivos:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, a in enumerate(archivos[:100], 1):
                periodo = f"{a['anio']}-{a['mes']}" if a.get("anio") else "fecha desconocida"
                parts.append(f"{i}. {a['titulo']} [{periodo}, {a.get('formato')}]")
                parts.append(f"   {a['url']}")
            if len(archivos) > 100:
                parts.append(f"... y {len(archivos) - 100} más (usa query para acotar, o format=json)")
            parts.append("")
            parts.append(f"Fuente: {data.get('url_fuente')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

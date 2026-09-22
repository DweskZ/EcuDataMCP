from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import energia_ecuador_snapshot_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_get_energia_ecuador_snapshot_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Recuperar snapshot del portal nacional de cortes (energia-ecuador.com, 2024)",
        annotations=READ_ONLY,
    )
    @log_tool
    async def get_energia_ecuador_snapshot(
        query: str = "", format: Literal["text", "json"] = "text"
    ) -> dict[str, Any]:
        """
        Recover, via the Wayback Machine, the national blackout-schedule
        aggregator the Ministry of Energy and Mines briefly ran during the
        2024 crisis at energia-ecuador.com ("Portal para actualización de
        racionamiento energético"). The domain itself is dead (parked
        since 2025) and the site went behind a Cloudflare bot-block within
        days of launch, so only one of its nine distributor pages was
        fully archived: Empresa Eléctrica Quito, a single frozen snapshot
        from 2024-04-24 (province/canton/sector-level rotation for
        Pichincha, 40 rows). Centrosur, CNEL, Emelnorte, EEASA, and four
        other distributors' pages are confirmed to have existed (via the
        site's own archived sitemap) but were never successfully
        archived — not recoverable from this or any other source found so
        far.

        This is a one-time historical snapshot, not an ongoing series —
        there is no newer page to discover.

        Args:
            query: Free text matched (accent-insensitive) against canton
                or sectores. Empty returns all rows.
            format: text | json
        """
        try:
            result = await energia_ecuador_snapshot_client.get_energia_ecuador_snapshot(
                query=query
            )
        except Exception as e:
            raise ToolError(
                f"Error al recuperar el snapshot de energia-ecuador.com desde la Wayback Machine: {e}"
            ) from e

        def to_text(data: dict) -> str:
            filas = data.get("filas") or []
            parts = [
                (
                    f"energia-ecuador.com (snapshot {data.get('fecha_snapshot')}, solo EEQ) — "
                    f"{data['total']} resultado(s) de {data['total_en_snapshot']} filas"
                ),
                "",
            ]
            if not filas:
                parts.append("Sin resultados.")
                return "\n".join(parts)
            for i, f in enumerate(filas[:100], 1):
                sectores = (f.get("sectores") or "").replace("\n", " / ")
                parts.append(
                    f"{i}. {f.get('provincia')}/{f.get('canton')} "
                    f"[{f.get('programacion_inicio')}-{f.get('programacion_fin')}]"
                )
                parts.append(f"   {sectores[:200]}")
            if len(filas) > 100:
                parts.append(f"... y {len(filas) - 100} más (usa query para acotar, o format=json)")
            parts.append("")
            parts.append(f"Fuente: {data.get('source')}")
            parts.append(f"Snapshot: {data.get('url_snapshot')}")
            return "\n".join(parts)

        return render_structured(result, format, text_builder=to_text)

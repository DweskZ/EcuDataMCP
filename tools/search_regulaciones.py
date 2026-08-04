from mcp.server.fastmcp import FastMCP

from helpers import gobec_client
from helpers.format_out import render_output
from helpers.gobec_client import _clean_html
from helpers.logging import log_tool


def register_search_regulaciones_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_regulaciones(
        query: str = "", page: int = 1, format: str = "text"
    ) -> str:
        """
        Search or list regulations published on Ecuador's gob.ec portal.

        Includes agreements, regulations and related norms with Registro Oficial
        references when available. With a query, scans several pages client-side
        (the API has no native search). Without a query, returns a paginated list.

        Args:
            query: Keywords (e.g. "datos personales", "tránsito", "LOTAIP")
            page: Page number when query is empty (1-based)
            format: text | json
        """
        try:
            if query.strip():
                regs = await gobec_client.find_regulaciones(query.strip(), max_pages=6)
            else:
                api_page = max(page - 1, 0)
                regs = await gobec_client.list_regulaciones(page=api_page)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al buscar regulaciones: {d['error']}",
            )

        payload = {
            "query": query,
            "page": page,
            "total": len(regs),
            "results": [
                {
                    "regulacion_id": reg.get("regulacion_id"),
                    "regulacion": _clean_html(reg.get("regulacion", "")).strip('"'),
                    "tipo": reg.get("tipo"),
                    "registro_oficial_numero": reg.get("registro_oficial_numero"),
                    "registro_oficial_fecha": reg.get("registro_oficial_fecha"),
                    "url": reg.get("url"),
                    "descripcion": _clean_html(reg.get("descripcion", ""))[:300],
                }
                for reg in regs[:20]
            ],
        }

        def to_text(data: dict) -> str:
            rows = data.get("results") or []
            if not rows:
                msg = "No se encontraron regulaciones"
                if data.get("query"):
                    msg += f" para '{data['query']}'"
                return msg + "."

            parts: list[str] = []
            if data.get("query"):
                parts.append(f"Regulaciones que coinciden con '{data['query']}':")
                parts.append(
                    f"Encontradas: {data['total']} (máx. páginas escaneadas)\n"
                )
            else:
                parts.append(f"Regulaciones en gob.ec (página {data['page']}):")
                parts.append(f"Mostrando {len(rows)} resultados\n")

            for i, reg in enumerate(rows, 1):
                parts.append(f"{i}. {reg.get('regulacion') or 'Sin título'}")
                parts.append(f"   ID: {reg.get('regulacion_id', '?')}")
                if reg.get("tipo"):
                    parts.append(f"   Tipo: {reg['tipo']}")
                if reg.get("registro_oficial_numero"):
                    ro = reg["registro_oficial_numero"]
                    if reg.get("registro_oficial_fecha"):
                        ro += f" ({reg['registro_oficial_fecha']})"
                    parts.append(f"   Registro Oficial: {ro}")
                if reg.get("descripcion"):
                    parts.append(f"   Descripción: {reg['descripcion']}")
                if reg.get("url"):
                    parts.append(f"   URL: {reg['url']}")
                parts.append("")
            if data["total"] > 20:
                parts.append(f"... y {data['total'] - 20} más.")
            parts.append(
                "Tip: Usa get_regulacion_info(regulacion_id='...') para el detalle y el PDF."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

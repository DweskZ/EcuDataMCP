from mcp.server.fastmcp import FastMCP

from helpers import anda_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_anda_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_anda(query: str = "", limit: int = 10, format: str = "text") -> str:
        """
        Search INEC's ANDA catalog (anda.inec.gob.ec) of surveys and censuses.

        ANDA runs on NADA (World Bank/IHSN), separate from datosabiertos.gob.ec.
        It catalogs 437+ INEC surveys/censuses with metadata (title, year,
        authoring entity). Not every entry has downloadable microdata — many are
        aggregate-only publications (e.g. price indices); each result says so.

        Use short, specific keywords in Spanish — multi-word queries are matched
        loosely, not as a strict AND.

        Args:
            query: Search keywords (e.g. "empleo", "REEM", "censo agropecuario")
            limit: Max results (default: 10, max: 50)
            format: text | json
        """
        try:
            result = await anda_client.search_catalog(query=query, limit=limit)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al buscar en ANDA: {d['error']}",
            )

        rows = result.get("rows", [])
        payload = {
            "query": query,
            "total": result.get("found", 0),
            "results": [
                {
                    "id": r.get("id"),
                    "idno": r.get("idno"),
                    "titulo": r.get("title"),
                    "anio": r.get("year_start"),
                    "entidad": r.get("authoring_entity"),
                    "microdatos_disponibles": anda_client.has_microdata(r),
                    "url": r.get("url"),
                }
                for r in rows
            ],
        }

        def to_text(data: dict) -> str:
            rows = data.get("results") or []
            if not rows:
                return f"No se encontraron encuestas en ANDA para: '{data['query']}'"
            parts = [
                f"Se encontraron {data['total']} encuesta(s) en ANDA para: '{data['query']}'",
                f"Mostrando {len(rows)} resultados:\n",
            ]
            for i, r in enumerate(rows, 1):
                parts.append(f"{i}. {r.get('titulo', 'Sin título')} ({r.get('anio', '?')})")
                parts.append(f"   ID: {r.get('id')} · idno: {r.get('idno')}")
                parts.append(f"   Entidad: {r.get('entidad')}")
                microdatos = "sí" if r.get("microdatos_disponibles") else "no (solo agregados)"
                parts.append(f"   Microdatos disponibles: {microdatos}")
                parts.append(f"   URL: {r.get('url')}")
                parts.append("")
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

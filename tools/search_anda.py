from functools import partial

from mcp.server.fastmcp import FastMCP

from helpers import anda_client
from helpers.format_out import render_output
from helpers.logging import log_tool
from helpers.text_utils import strip_accents

# ANDA's own full-text search (`sk`) is loose — it ranks by relevance across
# a broad blob of fields rather than requiring every query word to match, so
# a search for "ENESEM" also surfaces REEM, price indices, etc. Fetch a wider
# candidate batch and filter locally so results actually contain the query.
_FETCH_SIZE = 100

_strip_accents = partial(strip_accents, lower=False)


def _matches_query(row: dict, words: list[str]) -> bool:
    blob = _strip_accents(
        f"{row.get('title', '')} {row.get('subtitle', '')} "
        f"{row.get('idno', '')} {row.get('authoring_entity', '')}"
    ).lower()
    return all(w in blob for w in words)


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
        Start any INEC search here — it's the broadest index. When a result
        shows microdatos_disponibles=false, the operation exists but its actual
        published data lives on ecuadorencifras.gob.ec instead: try
        search_inec_estadisticas with the same query.

        Follow up with get_anda_survey_info(idno) for full metadata on one survey.

        Args:
            query: Search keywords (e.g. "empleo", "REEM", "censo agropecuario")
            limit: Max results (default: 10, max: 50)
            format: text | json
        """
        limit = min(max(limit, 1), 50)
        words = [_strip_accents(w.lower()) for w in query.split() if len(w) >= 2]
        try:
            if query:
                result = await anda_client.search_catalog(query=query, limit=_FETCH_SIZE)
                candidates = result.get("rows", [])
                matched = [r for r in candidates if _matches_query(r, words)]
                total_scanned = len(candidates)
            else:
                result = await anda_client.search_catalog(limit=limit)
                matched = result.get("rows", [])
                total_scanned = len(matched)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al buscar en ANDA: {d['error']}",
            )

        total = len(matched)
        payload = {
            "query": query,
            "total": total,
            "total_scanned": total_scanned,
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
                for r in matched[:limit]
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

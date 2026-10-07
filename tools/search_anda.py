from functools import partial
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import anda_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.text_utils import strip_accents
from helpers.tool_meta import READ_ONLY

# ANDA's own full-text search (`sk`) is loose — it ranks by relevance across
# a broad blob of fields rather than requiring every query word to match, so
# a search for "ENESEM" also surfaces REEM, price indices, etc. Page through
# every candidate and filter locally so results actually contain the query.

_strip_accents = partial(strip_accents, lower=False)


def _matches_query(row: dict, words: list[str]) -> bool:
    blob = _strip_accents(
        f"{row.get('title', '')} {row.get('subtitle', '')} "
        f"{row.get('idno', '')} {row.get('authoring_entity', '')}"
    ).lower()
    return all(w in blob for w in words)


def register_search_anda_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Buscar encuestas y censos en ANDA",
        description=(
            "Search INEC's ANDA catalog of 437+ surveys and censuses; the broadest "
            "INEC index. Entries without microdata point to "
            "search_inec_estadisticas. Next: get_anda_survey_info."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def search_anda(
        query: str = "",
        limit: int = 10,
        page: int = 1,
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
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

        microdatos_disponibles=true means ANDA flags the study as having
        microdata, not that files are attached: some studies (e.g. general
        deaths 2012, 2017-2019) list none and host them on ecuadorencifras.gob.ec
        — see get_inec_estadistica_files.

        Follow up with get_anda_survey_info(idno) for full metadata on one survey.
        The numeric "id" also works as the identifier in the follow-up tools.

        Args:
            query: Search keywords (e.g. "empleo", "REEM", "censo agropecuario")
            limit: Results per page (default: 10, max: 50)
            page: Page of results, 1-based (default: 1); see total/total_pages
            format: text | json
        """
        limit = min(max(limit, 1), 50)
        page = max(page, 1)
        words = [_strip_accents(w.lower()) for w in query.split() if len(w) >= 2]
        try:
            if query:
                candidates = await anda_client.search_catalog_all(query=query)
                matched = [r for r in candidates if _matches_query(r, words)]
                total_scanned = len(candidates)
                total_catalog = len(matched)
            else:
                result = await anda_client.search_catalog(limit=limit, page=page)
                matched = result.get("rows", [])
                total_scanned = len(matched)
                total_catalog = int(result.get("found") or 0)
        except Exception as e:
            raise ToolError(f"Error al buscar en ANDA: {e}") from e

        # With a query the match list is already complete, so slice it locally;
        # without one the server paged it for us.
        total = total_catalog
        shown = matched[(page - 1) * limit : page * limit] if query else matched
        payload = {
            "query": query,
            "total": total,
            "page": page,
            "total_pages": max(-(-total // limit), 1),
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
                for r in shown
            ],
        }

        def to_text(data: dict) -> str:
            rows = data.get("results") or []
            if not rows:
                return f"No se encontraron encuestas en ANDA para: '{data['query']}'"
            parts = [
                f"Se encontraron {data['total']} encuesta(s) en ANDA para: '{data['query']}'",
                f"Página {data['page']} de {data['total_pages']} ({len(rows)} resultados):\n",
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

        return render_structured(payload, format, text_builder=to_text)

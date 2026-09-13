from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import ckan_client
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_search_datasets_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Buscar datasets en el portal de datos abiertos", annotations=READ_ONLY)
    @log_tool
    async def search_datasets(
        query: str = "",
        page: int = 1,
        page_size: int = 20,
        category: str = "",
        sort: Literal["relevance", "recent"] = "relevance",
        source: ckan_client.CkanSource = "nacional",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Search for datasets on Ecuador's open data portal (www.datosabiertos.gob.ec).

        This is the starting point for exploring government data from 98+ public institutions.
        Use short, specific queries in Spanish for best results.

        Typical workflow: search_datasets → list_dataset_resources → preview_resource_data

        Args:
            query: Search keywords (e.g. "empleo", "salud", "presupuesto", "SRI recaudación").
                   Optional when sort="recent" — omit it to browse newly
                   published/updated datasets without a keyword.
            page: Page number (1-based, default: 1)
            page_size: Results per page (default: 20, max: 100)
            category: Optional category filter (e.g. "sal" for Salud, "edu" for Educación).
                      Use list_categories to see all available categories.
            sort: "relevance" (default, CKAN's own ranking) or "recent"
                  (sort by metadata_modified descending, to discover newly
                  added or freshly refreshed datasets)
            source: "nacional" (www.datosabiertos.gob.ec, default), "cuenca"
                    (cuencaendatos.cuenca.gob.ec, the Cuenca municipal open-data
                    portal), "latacunga" (datosabiertos.latacunga.gob.ec,
                    the Latacunga municipal open-data portal) — separate,
                    smaller CKAN catalogs — or "iadb" (data.iadb.org, the
                    Inter-American Development Bank's open-data portal — NOT
                    Ecuador-only, a regional/global catalog: Latin Macro Watch
                    macro/financial indicators for 26 LAC countries, the
                    World Bank/IADB Database of Political Institutions for
                    ~180 countries)
            format: text | json
        """
        page_size = min(max(page_size, 1), 100)
        start = (max(page, 1) - 1) * page_size
        recent = sort == "recent"
        effective_query = query or ("*:*" if recent else "")
        sort_param = "metadata_modified desc" if recent else ""
        try:
            result = await ckan_client.search_datasets(
                query=effective_query,
                rows=page_size,
                start=start,
                category=category,
                sort=sort_param,
                source=source,
            )
        except Exception as e:
            raise ToolError(f"Error al buscar datasets: {e}") from e

        datasets = result.get("results", [])
        total = result.get("count", 0)
        site = ckan_client.site_url(source).rstrip("/")
        payload = {
            "query": query,
            "recent": recent,
            "total": total,
            "page": page,
            "results": datasets,
            "site": site,
        }

        def to_text(data: dict) -> str:
            rows = data.get("results") or []
            if not rows:
                if data["recent"] and not data["query"]:
                    return "No se encontraron datasets recientes."
                return f"No se encontraron datasets para: '{data['query']}'"
            header = (
                "Datasets actualizados recientemente (CKAN)"
                if data["recent"] and not data["query"]
                else f"Se encontraron {data['total']} dataset(s) para: '{data['query']}'"
            )
            parts = [
                header,
                f"Página {data['page']} (mostrando {len(rows)} resultados):\n",
            ]
            for i, ds in enumerate(rows, 1):
                parts.append(f"{i}. {ds.get('title', 'Sin título')}")
                parts.append(f"   ID: {ds.get('name') or ds.get('id')}")
                notes = ds.get("notes", "")
                if notes:
                    parts.append(f"   Descripción: {notes[:200]}...")
                org = ds.get("organization")
                if org and isinstance(org, dict):
                    parts.append(f"   Organización: {org.get('title', '')}")
                tags = ds.get("tags", [])
                if tags:
                    tag_names = [
                        t.get("display_name", t.get("name", "")) for t in tags[:5]
                    ]
                    parts.append(f"   Tags: {', '.join(tag_names)}")
                num_res = ds.get("num_resources", len(ds.get("resources", [])))
                parts.append(f"   Recursos: {num_res}")
                slug = ds.get("name", ds.get("id", ""))
                parts.append(f"   URL: {data['site']}/dataset/{slug}")
                parts.append("")
            return "\n".join(parts)

        return render_structured(payload, format, text_builder=to_text)

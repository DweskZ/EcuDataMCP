from mcp.server.fastmcp import FastMCP

from helpers import ckan_client, env_config
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_datasets_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_datasets(
        query: str,
        page: int = 1,
        page_size: int = 20,
        category: str = "",
        format: str = "text",
    ) -> str:
        """
        Search for datasets on Ecuador's open data portal (www.datosabiertos.gob.ec).

        This is the starting point for exploring government data from 98+ public institutions.
        Use short, specific queries in Spanish for best results.

        Typical workflow: search_datasets → list_dataset_resources → preview_resource_data

        Args:
            query: Search keywords (e.g. "empleo", "salud", "presupuesto", "SRI recaudación")
            page: Page number (1-based, default: 1)
            page_size: Results per page (default: 20, max: 100)
            category: Optional category filter (e.g. "sal" for Salud, "edu" for Educación).
                      Use list_categories to see all available categories.
            format: text | json
        """
        start = (max(page, 1) - 1) * page_size
        try:
            result = await ckan_client.search_datasets(
                query=query, rows=page_size, start=start, category=category
            )
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al buscar datasets: {d['error']}",
            )

        datasets = result.get("results", [])
        total = result.get("count", 0)
        site = env_config.get_base_url("ckan_site").rstrip("/")
        payload = {
            "query": query,
            "total": total,
            "page": page,
            "results": datasets,
            "site": site,
        }

        def to_text(data: dict) -> str:
            rows = data.get("results") or []
            if not rows:
                return f"No se encontraron datasets para: '{data['query']}'"
            parts = [
                f"Se encontraron {data['total']} dataset(s) para: '{data['query']}'",
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

        return render_output(payload, format, text_builder=to_text)

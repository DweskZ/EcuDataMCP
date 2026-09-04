from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_list_recent_datasets_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_recent_datasets(
        page: int = 1, page_size: int = 15, source: str = "nacional", format: str = "text"
    ) -> str:
        """
        List the most recently updated datasets on Ecuador's open data portal.

        Useful to discover new or freshly refreshed government data without a
        specific keyword. Sorted by metadata_modified descending.

        Args:
            page: Page number (1-based, default 1)
            page_size: Results per page (default 15, max 50)
            source: "nacional" (default), "cuenca" (Cuenca municipal portal), or
                    "latacunga" (Latacunga municipal portal)
            format: text | json
        """
        page = max(page, 1)
        page_size = min(max(page_size, 1), 50)
        start = (page - 1) * page_size

        try:
            result = await ckan_client.recent_datasets(
                rows=page_size, start=start, source=source
            )
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al listar datasets recientes: {d['error']}",
            )

        datasets = result.get("results") or []
        total = result.get("count", 0)
        site = ckan_client.site_url(source).rstrip("/")
        payload = {
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": [
                {
                    "id": ds.get("id"),
                    "name": ds.get("name"),
                    "title": ds.get("title"),
                    "organization": (ds.get("organization") or {}).get("title"),
                    "metadata_modified": ds.get("metadata_modified"),
                    "num_resources": ds.get("num_resources"),
                    "url": f"{site}/dataset/{ds.get('name') or ds.get('id')}",
                }
                for ds in datasets
            ],
        }

        def to_text(data: dict) -> str:
            rows = data.get("results") or []
            if not rows:
                return "No se encontraron datasets recientes."
            parts = [
                "Datasets actualizados recientemente (CKAN)",
                (
                    f"Total en catálogo: {data['total']} | Página {data['page']} "
                    f"(mostrando {len(rows)})\n"
                ),
            ]
            for i, ds in enumerate(rows, 1):
                parts.append(f"{i}. {ds.get('title') or 'Sin título'}")
                parts.append(f"   ID: {ds.get('name') or ds.get('id')}")
                if ds.get("organization"):
                    parts.append(f"   Org: {ds['organization']}")
                if ds.get("metadata_modified"):
                    parts.append(f"   Modificado: {ds['metadata_modified']}")
                if ds.get("url"):
                    parts.append(f"   URL: {ds['url']}")
                parts.append("")
            parts.append(
                "Tip: usa get_dataset_info / list_dataset_resources / query_resource_data."
            )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

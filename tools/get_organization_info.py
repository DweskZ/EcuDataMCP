from mcp.server.mcpserver import MCPServer

from helpers import ckan_client
from helpers.format_out import render_output
from helpers.logging import log_tool
from helpers.text_utils import strip_accents as _strip

_TEXT_DISPLAY_LIMIT = 60


def register_get_organization_info_tool(mcp: MCPServer) -> None:
    @mcp.tool()
    @log_tool
    async def get_organization_info(
        organization_id: str,
        query: str = "",
        source: str = "nacional",
        format: str = "text",
    ) -> str:
        """
        Get detailed information about a public institution and its published
        datasets — the main way to browse a CKAN organization's full package
        list, including large ones with no dedicated tool of their own
        (e.g. "sri-servicio-de-rentas-internas" —127 packages—,
        "ministerio-de-economia-y-finanzas" —97—, "ieps" —106—, "cosede" —88—,
        "ipaip" —70—, "mag" —69—; get the exact slug from
        search_organizations first if unsure).

        Returns the institution name, description, dataset count, and its
        datasets. format=json always returns every dataset; format=text caps
        display and tells you how many more exist — use query to narrow a
        large organization down instead of scrolling past the cap.

        Args:
            organization_id: The organization slug (e.g. "sri-servicio-de-rentas-internas")
            query: Free text matched (accent-insensitive) against each
                dataset's title. Empty returns all datasets.
            source: "nacional" (default), "cuenca" (Cuenca municipal portal),
                    "latacunga" (Latacunga municipal portal), or "iadb" (IADB's
                    open-data portal, data.iadb.org — NOT Ecuador-only, a
                    regional/global catalog)
            format: text | json
        """
        try:
            org = await ckan_client.get_organization(organization_id, source=source)
        except Exception as e:
            return render_output(
                {"error": str(e), "organization_id": organization_id},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        site = ckan_client.site_url(source).rstrip("/")
        datasets = org.get("packages") or []
        q = _strip(query)
        if q:
            datasets = [
                ds
                for ds in datasets
                if q in _strip(ds.get("title") or ds.get("name") or "")
            ]
        payload = {
            "name": org.get("name"),
            "title": org.get("title"),
            "url": f"{site}/organization/{org['name']}" if org.get("name") else None,
            "description": org.get("description"),
            "package_count": org.get("package_count", 0),
            "state": org.get("state"),
            "query": query or None,
            "datasets": [
                {
                    "id": ds.get("id") or ds.get("name"),
                    "name": ds.get("name"),
                    "title": ds.get("title") or ds.get("name") or "Sin título",
                }
                for ds in datasets
            ],
            "datasets_total": len(datasets),
        }

        def to_text(data: dict) -> str:
            parts = [
                f"Organización: {data.get('title') or 'Desconocida'}",
                "",
            ]
            if data.get("name"):
                parts.append(f"ID: {data['name']}")
                parts.append(f"URL: {data.get('url')}")
            if data.get("description"):
                parts.append(f"Descripción: {str(data['description'])[:500]}")
            parts.append(f"Total de datasets: {data.get('package_count', 0)}")
            parts.append(f"Estado: {data.get('state') or 'Desconocido'}")
            shown_datasets = data.get("datasets") or []
            if data.get("query"):
                parts.append(f"Filtrado por: '{data['query']}' ({data.get('datasets_total', 0)} coincidencia(s))")
            if shown_datasets:
                parts.append("")
                parts.append(f"Datasets publicados ({data.get('datasets_total', 0)}):")
                for i, ds in enumerate(shown_datasets[:_TEXT_DISPLAY_LIMIT], 1):
                    parts.append(f"  {i}. {ds['title']}")
                    parts.append(f"     ID: {ds.get('id', '')}")
                total = data.get("datasets_total", 0)
                if total > _TEXT_DISPLAY_LIMIT:
                    parts.append(
                        f"  ... y {total - _TEXT_DISPLAY_LIMIT} más "
                        "(usa query para acotar, o format=json para verlos todos)"
                    )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

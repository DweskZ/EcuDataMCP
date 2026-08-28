from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_get_organization_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_organization_info(
        organization_id: str, source: str = "nacional", format: str = "text"
    ) -> str:
        """
        Get detailed information about a public institution and its published datasets.

        Returns the institution name, description, dataset count, and a list of its datasets.

        Args:
            organization_id: The organization slug (e.g. "sri-servicio-de-rentas-internas")
            source: "nacional" (default) or "cuenca" (Cuenca municipal portal)
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

        site = ckan_client.site_url(source)
        datasets = org.get("packages") or []
        payload = {
            "name": org.get("name"),
            "title": org.get("title"),
            "url": f"{site}organization/{org['name']}" if org.get("name") else None,
            "description": org.get("description"),
            "package_count": org.get("package_count", 0),
            "state": org.get("state"),
            "datasets": [
                {
                    "id": ds.get("id") or ds.get("name"),
                    "name": ds.get("name"),
                    "title": ds.get("title") or ds.get("name") or "Sin título",
                }
                for ds in datasets[:25]
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
            if data.get("datasets"):
                parts.append("")
                parts.append(f"Datasets publicados ({data.get('datasets_total', 0)}):")
                for i, ds in enumerate(data["datasets"], 1):
                    parts.append(f"  {i}. {ds['title']}")
                    parts.append(f"     ID: {ds.get('id', '')}")
                total = data.get("datasets_total", 0)
                shown = len(data["datasets"])
                if total > shown:
                    parts.append(f"  ... y {total - shown} más")
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

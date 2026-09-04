from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_search_organizations_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def search_organizations(
        query: str = "",
        page: int = 1,
        page_size: int = 20,
        source: str = "nacional",
        format: str = "text",
    ) -> str:
        """
        Search for public institutions that publish data on Ecuador's open data portal.

        There are 98+ organizations including INEC, SRI, Ministerio de Salud, BCE, etc.

        Args:
            query: Optional search term (e.g. "salud", "SRI", "INEC")
            page: Page number (1-based, default: 1)
            page_size: Results per page (default: 20, max: 100)
            source: "nacional" (default), "cuenca" (Cuenca municipal portal), or
                    "latacunga" (Latacunga municipal portal)
            format: text | json
        """
        page_size = min(max(page_size, 1), 100)
        offset = (max(page, 1) - 1) * page_size
        try:
            orgs = await ckan_client.list_organizations(
                query=query, limit=page_size, offset=offset, source=source
            )
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        payload = {
            "query": query or None,
            "page": page,
            "page_size": page_size,
            # CKAN's organization_list has no total-count field to report --
            # this is the page size actually returned, not a corpus total.
            "count_esta_pagina": len(orgs),
            "posiblemente_hay_mas": len(orgs) == page_size,
            "results": [
                {
                    "name": org.get("name"),
                    "title": org.get("title")
                    or org.get("display_name")
                    or "Sin nombre",
                    "package_count": org.get("package_count", 0),
                    "description": org.get("description"),
                }
                for org in orgs
            ],
        }

        if not orgs:
            return render_output(
                payload,
                format,
                text_builder=lambda d: (
                    "No se encontraron organizaciones"
                    + (f" para: '{d['query']}'" if d.get("query") else "")
                ),
            )

        def to_text(data: dict) -> str:
            parts = []
            if data.get("query"):
                parts.append(f"Organizaciones que coinciden con '{data['query']}':\n")
            else:
                parts.append(f"Organizaciones (página {data['page']}):\n")
            for i, org in enumerate(data["results"], 1):
                parts.append(f"{i}. {org['title']}")
                parts.append(f"   ID: {org.get('name')}")
                parts.append(f"   Datasets: {org.get('package_count', 0)}")
                if org.get("description"):
                    parts.append(f"   Descripción: {str(org['description'])[:150]}")
                parts.append("")
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

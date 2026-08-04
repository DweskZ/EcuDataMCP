from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.format_out import render_output
from helpers.logging import log_tool


def _format_size(size: int | None) -> str:
    if not size or not isinstance(size, (int, float)):
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


def register_list_dataset_resources_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def list_dataset_resources(dataset_id: str, format: str = "text") -> str:
        """
        List all resources (files) in a dataset with their metadata.

        Returns resource ID, title, format, size, and download URL for each file.
        Next step: use preview_resource_data on a CSV resource to see its contents,
        or use get_resource_info for detailed metadata.

        Args:
            dataset_id: The dataset ID or slug
            format: text | json
        """
        try:
            dataset = await ckan_client.get_dataset(dataset_id)
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        resources = dataset.get("resources", [])
        payload = {
            "dataset_id": dataset.get("id", dataset_id),
            "title": dataset.get("title", "Desconocido"),
            "total": len(resources),
            "resources": [
                {
                    "id": res.get("id"),
                    "name": res.get("name") or res.get("description") or "Sin título",
                    "format": res.get("format"),
                    "size": res.get("size"),
                    "size_label": _format_size(res.get("size")),
                    "mimetype": res.get("mimetype"),
                    "description": res.get("description"),
                    "url": res.get("url"),
                }
                for res in resources
                if res.get("id")
            ],
        }

        def to_text(data: dict) -> str:
            rows = data.get("resources") or []
            parts = [
                f"Recursos del dataset: {data.get('title')}",
                f"Dataset ID: {data.get('dataset_id')}",
                f"Total de recursos: {data.get('total', 0)}\n",
            ]
            if not rows:
                parts.append("Este dataset no tiene recursos.")
                return "\n".join(parts)
            for i, res in enumerate(rows, 1):
                parts.append(f"{i}. {res.get('name')}")
                parts.append(f"   Resource ID: {res.get('id')}")
                if res.get("format"):
                    parts.append(f"   Formato: {res['format']}")
                if res.get("size_label"):
                    parts.append(f"   Tamaño: {res['size_label']}")
                if res.get("mimetype"):
                    parts.append(f"   MIME: {res['mimetype']}")
                if res.get("description") and res.get("name"):
                    parts.append(f"   Descripción: {str(res['description'])[:200]}")
                if res.get("url"):
                    parts.append(f"   URL: {res['url']}")
                parts.append("")
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

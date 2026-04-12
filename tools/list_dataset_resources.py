from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
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
    async def list_dataset_resources(dataset_id: str) -> str:
        """
        List all resources (files) in a dataset with their metadata.

        Returns resource ID, title, format, size, and download URL for each file.
        Next step: use preview_resource_data on a CSV resource to see its contents,
        or use get_resource_info for detailed metadata.

        Args:
            dataset_id: The dataset ID or slug
        """
        try:
            dataset = await ckan_client.get_dataset(dataset_id)
        except Exception as e:
            return f"Error: {e}"

        resources = dataset.get("resources", [])
        title = dataset.get("title", "Desconocido")

        parts = [
            f"Recursos del dataset: {title}",
            f"Dataset ID: {dataset.get('id', dataset_id)}",
            f"Total de recursos: {len(resources)}\n",
        ]

        if not resources:
            parts.append("Este dataset no tiene recursos.")
            return "\n".join(parts)

        for i, res in enumerate(resources, 1):
            rid = res.get("id")
            if not rid:
                continue
            name = res.get("name") or res.get("description") or "Sin título"
            parts.append(f"{i}. {name}")
            parts.append(f"   Resource ID: {rid}")

            if res.get("format"):
                parts.append(f"   Formato: {res['format']}")
            size_str = _format_size(res.get("size"))
            if size_str:
                parts.append(f"   Tamaño: {size_str}")
            if res.get("mimetype"):
                parts.append(f"   MIME: {res['mimetype']}")
            if res.get("description") and res.get("name"):
                parts.append(f"   Descripción: {res['description'][:200]}")
            if res.get("url"):
                parts.append(f"   URL: {res['url']}")

            parts.append("")

        return "\n".join(parts)

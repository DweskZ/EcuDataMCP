import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client, env_config
from helpers.logging import log_tool


def _format_size(size: int | None) -> str:
    if not size or not isinstance(size, (int, float)):
        return "Desconocido"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"


def register_get_resource_info_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def get_resource_info(resource_id: str) -> str:
        """
        Get detailed information about a specific resource (file) from Ecuador's open data portal.

        Returns format, size, MIME type, download URL, and dataset association.
        For CSV files, you can then use preview_resource_data to see the actual data.

        Args:
            resource_id: The resource UUID
        """
        try:
            res = await ckan_client.get_resource(resource_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"Error: Recurso con ID '{resource_id}' no encontrado."
            return f"Error: HTTP {e.response.status_code} - {e}"
        except Exception as e:
            return f"Error: {e}"

        site = env_config.get_base_url("ckan_site")
        name = res.get("name") or res.get("description") or "Sin título"
        parts = [f"Recurso: {name}", ""]

        parts.append(f"ID: {res.get('id')}")
        if res.get("package_id"):
            parts.append(f"Dataset ID: {res['package_id']}")
            parts.append(f"Dataset URL: {site}dataset/{res['package_id']}")

        parts.append("")
        parts.append(f"Formato: {res.get('format', 'Desconocido')}")
        parts.append(f"Tamaño: {_format_size(res.get('size'))}")
        if res.get("mimetype"):
            parts.append(f"MIME type: {res['mimetype']}")

        if res.get("url"):
            parts.append("")
            parts.append(f"URL de descarga: {res['url']}")

        if res.get("description"):
            parts.append("")
            parts.append(f"Descripción: {res['description']}")

        if res.get("created"):
            parts.append("")
            parts.append(f"Creado: {res['created']}")
        if res.get("last_modified"):
            parts.append(f"Última modificación: {res['last_modified']}")

        fmt = (res.get("format") or "").upper()
        if fmt in ("CSV", "XLS", "XLSX", "TSV"):
            parts.append("")
            parts.append(
                "Tip: Usa preview_resource_data con este resource_id para ver las primeras filas de datos."
            )

        return "\n".join(parts)

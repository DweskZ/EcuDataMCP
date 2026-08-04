import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client, env_config
from helpers.format_out import render_output
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
    async def get_resource_info(resource_id: str, format: str = "text") -> str:
        """
        Get detailed information about a specific resource (file) from Ecuador's open data portal.

        Returns format, size, MIME type, download URL, and dataset association.
        For CSV files, you can then use preview_resource_data to see the actual data.

        Args:
            resource_id: The resource UUID
            format: text | json
        """
        try:
            res = await ckan_client.get_resource(resource_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return render_output(
                    {"error": "not_found", "resource_id": resource_id},
                    format,
                    text_builder=lambda d: (
                        f"Error: Recurso con ID '{d['resource_id']}' no encontrado."
                    ),
                )
            return render_output(
                {"error": f"HTTP {e.response.status_code}", "detail": str(e)},
                format,
                text_builder=lambda d: f"Error: {d['error']} - {d['detail']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error: {d['error']}",
            )

        site = env_config.get_base_url("ckan_site")
        name = res.get("name") or res.get("description") or "Sin título"
        package_id = res.get("package_id")
        payload = {
            "id": res.get("id"),
            "name": name,
            "package_id": package_id,
            "dataset_url": f"{site}dataset/{package_id}" if package_id else None,
            "format": res.get("format"),
            "size": res.get("size"),
            "size_label": _format_size(res.get("size")),
            "mimetype": res.get("mimetype"),
            "url": res.get("url"),
            "description": res.get("description"),
            "created": res.get("created"),
            "last_modified": res.get("last_modified"),
        }

        def to_text(data: dict) -> str:
            parts = [f"Recurso: {data['name']}", ""]
            parts.append(f"ID: {data.get('id')}")
            if data.get("package_id"):
                parts.append(f"Dataset ID: {data['package_id']}")
                parts.append(f"Dataset URL: {data.get('dataset_url')}")
            parts.append("")
            parts.append(f"Formato: {data.get('format') or 'Desconocido'}")
            parts.append(f"Tamaño: {data.get('size_label')}")
            if data.get("mimetype"):
                parts.append(f"MIME type: {data['mimetype']}")
            if data.get("url"):
                parts.append("")
                parts.append(f"URL de descarga: {data['url']}")
            if data.get("description"):
                parts.append("")
                parts.append(f"Descripción: {data['description']}")
            if data.get("created"):
                parts.append("")
                parts.append(f"Creado: {data['created']}")
            if data.get("last_modified"):
                parts.append(f"Última modificación: {data['last_modified']}")
            fmt = (data.get("format") or "").upper()
            if fmt in ("CSV", "XLS", "XLSX", "TSV"):
                parts.append("")
                parts.append(
                    "Tip: Usa preview_resource_data con este resource_id "
                    "para ver las primeras filas de datos."
                )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

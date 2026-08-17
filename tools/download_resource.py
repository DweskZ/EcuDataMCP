import base64

import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.csv_reader import MAX_DOWNLOAD_BYTES, download_bytes
from helpers.format_out import render_output
from helpers.logging import log_tool


def register_download_resource_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def download_resource(resource_id: str, format: str = "text") -> str:
        """
        Download a resource's raw bytes from Ecuador's open data portal, base64-encoded.

        Use this for formats preview_resource_data can't parse into a table
        (.rar, legacy .xls, or anything unrecognized) — it fetches the file
        as-is instead of trying to read it. Max size: 5 MB (same cap as
        preview_resource_data). Larger files come back with an error and the
        direct URL instead, since they'd be too big to embed in a response.

        Args:
            resource_id: The resource UUID (get it from list_dataset_resources)
            format: text | json (json includes content_base64)
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
                text_builder=lambda d: f"Error al obtener metadata del recurso: {d['error']}",
            )

        url = res.get("url")
        if not url:
            return render_output(
                {"error": "sin_url", "resource_id": resource_id},
                format,
                text_builder=lambda _: "Error: Este recurso no tiene URL de descarga.",
            )

        name = res.get("name") or res.get("description") or "Sin título"
        fmt = (res.get("format") or "").upper() or None

        try:
            content, truncated = await download_bytes(url)
        except httpx.HTTPError as e:
            return render_output(
                {"error": f"download_failed: {e}", "url": url},
                format,
                text_builder=lambda d: f"Error al descargar el archivo: {d['error']}",
            )

        if truncated:
            max_mb = MAX_DOWNLOAD_BYTES // (1024 * 1024)
            return render_output(
                {
                    "error": "demasiado_grande",
                    "resource_id": resource_id,
                    "name": name,
                    "url": url,
                    "max_bytes": MAX_DOWNLOAD_BYTES,
                },
                format,
                text_builder=lambda d: (
                    f"'{d['name']}' supera el límite de {max_mb} MB para descarga "
                    f"vía MCP. Bájalo directamente desde: {d['url']}"
                ),
            )

        payload = {
            "resource_id": resource_id,
            "name": name,
            "url": url,
            "format": fmt,
            "size_bytes": len(content),
            "content_base64": base64.b64encode(content).decode("ascii"),
        }

        def to_text(data: dict) -> str:
            return (
                f"Descargado: {data['name']} ({data['size_bytes']} bytes"
                f"{', formato ' + data['format'] if data.get('format') else ''}).\n"
                'Usa format="json" para obtener el contenido en content_base64 '
                "(decodifícalo en base64 para reconstruir el archivo original)."
            )

        return render_output(payload, format, text_builder=to_text)

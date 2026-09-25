import base64
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import ckan_client
from helpers.csv_reader import MAX_DOWNLOAD_BYTES, download_bytes
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.tool_meta import READ_ONLY


def register_download_resource_tool(mcp: MCPServer) -> None:
    @mcp.tool(title="Descargar el archivo crudo de un recurso", annotations=READ_ONLY)
    @log_tool
    async def download_resource(
        resource_id: str,
        source: ckan_client.CkanSource = "nacional",
        format: Literal["text", "json"] = "text",
    ) -> dict[str, Any]:
        """
        Download a resource's raw bytes from Ecuador's open data portal, base64-encoded.

        Use this for formats preview_resource_data can't parse into a table
        (.rar, or anything unrecognized) — it fetches the file as-is instead
        of trying to read it. Max size: 5 MB (same
        cap as preview_resource_data). Larger files come back with an error
        and the direct URL instead, since they'd be too big to embed in a
        response.

        Call with format="json" to get the actual file content — the
        default format="text" only confirms the download and tells you to
        retry with json; it never includes content_base64.

        Args:
            resource_id: The resource UUID (get it from list_dataset_resources)
            source: "nacional" (default), "cuenca" (Cuenca municipal portal),
                    "latacunga" (Latacunga municipal portal), or "iadb" (IADB's
                    open-data portal, data.iadb.org — NOT Ecuador-only, a
                    regional/global catalog)
            format: text | json (json includes content_base64; use this to
                actually retrieve the file)
        """
        try:
            res = await ckan_client.get_resource(resource_id, source=source)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ToolError(f"Error: Recurso con ID '{resource_id}' no encontrado.") from e
            raise ToolError(f"Error: HTTP {e.response.status_code} - {e}") from e
        except Exception as e:
            raise ToolError(f"Error al obtener metadata del recurso: {e}") from e

        url = res.get("url")
        if not url:
            raise ToolError("Error: Este recurso no tiene URL de descarga.")

        name = res.get("name") or res.get("description") or "Sin título"
        fmt = (res.get("format") or "").upper() or None

        try:
            content, truncated = await download_bytes(url)
        except httpx.HTTPError as e:
            raise ToolError(f"Error al descargar el archivo: download_failed: {e}") from e

        if truncated:
            max_mb = MAX_DOWNLOAD_BYTES // (1024 * 1024)
            raise ToolError(
                f"'{name}' supera el límite de {max_mb} MB para descarga vía MCP. "
                f"Bájalo directamente desde: {url}"
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

        return render_structured(payload, format, text_builder=to_text)

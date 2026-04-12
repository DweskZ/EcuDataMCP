import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.csv_reader import format_table, preview_csv
from helpers.logging import log_tool


def register_preview_resource_data_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def preview_resource_data(resource_id: str, rows: int = 20) -> str:
        """
        Download and preview the contents of a CSV resource from Ecuador's open data portal.

        Downloads the file, parses it, and returns the first N rows as a formatted table.
        This lets you "see" the data without the user downloading anything.
        Works with CSV, TSV, and semicolon-delimited files. Max file size: 5 MB.

        Args:
            resource_id: The resource UUID (get it from list_dataset_resources)
            rows: Number of data rows to preview (default: 20, max: 100)
        """
        rows = min(max(rows, 1), 100)

        try:
            res = await ckan_client.get_resource(resource_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"Error: Recurso con ID '{resource_id}' no encontrado."
            return f"Error: HTTP {e.response.status_code} - {e}"
        except Exception as e:
            return f"Error al obtener metadata del recurso: {e}"

        url = res.get("url")
        if not url:
            return "Error: Este recurso no tiene URL de descarga."

        fmt = (res.get("format") or "").upper()
        if fmt not in ("CSV", "TSV", "TXT", ""):
            return (
                f"Este recurso tiene formato '{fmt}'. "
                f"preview_resource_data solo soporta archivos CSV/TSV. "
                f"Puedes descargar el archivo directamente desde: {url}"
            )

        name = res.get("name") or res.get("description") or "Sin título"

        try:
            result = await preview_csv(url, max_rows=rows)
        except httpx.HTTPError as e:
            return f"Error al descargar el archivo: {e}"
        except Exception as e:
            return f"Error al procesar el archivo CSV: {e}"

        headers = result["headers"]
        data_rows = result["rows"]

        if not headers:
            return f"El archivo '{name}' está vacío o no pudo ser parseado."

        parts = [
            f"Preview de: {name}",
            f"Resource ID: {resource_id}",
            f"Columnas: {len(headers)}",
            f"Filas mostradas: {result['total_rows_in_preview']}",
        ]
        if result["truncated"]:
            parts.append("⚠ Archivo truncado (excede 5 MB o tiene más filas)")
        parts.append("")
        parts.append(format_table(headers, data_rows))

        if result["truncated"]:
            parts.append("")
            parts.append(f"Descarga el archivo completo: {url}")

        return "\n".join(parts)

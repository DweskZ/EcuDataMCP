import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.csv_reader import format_table, preview_csv, preview_json, preview_xlsx
from helpers.logging import log_tool

_CSV_FORMATS = {"CSV", "TSV", "TXT", ""}
_JSON_FORMATS = {"JSON", "GEOJSON"}
_XLSX_FORMATS = {"XLSX", "XLS", "EXCEL"}


def register_preview_resource_data_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def preview_resource_data(resource_id: str, rows: int = 20) -> str:
        """
        Download and preview a resource from Ecuador's open data portal.

        Supports CSV/TSV, JSON/GeoJSON and Excel (XLSX). Returns the first N rows
        as a formatted table so the model can inspect data without a local download.
        Max download size: 5 MB. For large tabular DataStore resources prefer
        query_resource_data.

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
        name = res.get("name") or res.get("description") or "Sin título"

        try:
            if fmt in _CSV_FORMATS or (not fmt and url.lower().endswith((".csv", ".tsv", ".txt"))):
                result = await preview_csv(url, max_rows=rows)
            elif fmt in _JSON_FORMATS or url.lower().endswith((".json", ".geojson")):
                result = await preview_json(url, max_rows=rows)
            elif fmt in _XLSX_FORMATS or url.lower().endswith((".xlsx", ".xls")):
                if fmt == "XLS" or url.lower().endswith(".xls"):
                    return (
                        f"Este recurso es Excel legacy (.xls). "
                        f"Convierte a XLSX o descárgalo desde: {url}"
                    )
                result = await preview_xlsx(url, max_rows=rows)
            else:
                return (
                    f"Este recurso tiene formato '{fmt or 'desconocido'}'. "
                    f"preview_resource_data soporta CSV/TSV, JSON/GeoJSON y XLSX. "
                    f"Si está en DataStore prueba query_resource_data. "
                    f"Descarga directa: {url}"
                )
        except httpx.HTTPError as e:
            return f"Error al descargar el archivo: {e}"
        except Exception as e:
            return f"Error al procesar el archivo: {e}"

        headers = result["headers"]
        data_rows = result["rows"]

        if not headers:
            return f"El archivo '{name}' está vacío o no pudo ser parseado."

        parts = [
            f"Preview de: {name}",
            f"Resource ID: {resource_id}",
            f"Formato: {result.get('format', fmt or 'csv')}",
            f"Columnas: {len(headers)}",
            f"Filas mostradas: {result['total_rows_in_preview']}",
        ]
        if result.get("sheet"):
            parts.append(f"Hoja: {result['sheet']}")
        if result.get("total_records") is not None:
            parts.append(f"Registros totales (en archivo): {result['total_records']}")
        if result["truncated"]:
            parts.append("⚠ Archivo truncado (excede 5 MB o tiene más filas)")
        parts.append("")
        parts.append(format_table(headers, data_rows))

        if result["truncated"]:
            parts.append("")
            parts.append(f"Descarga el archivo completo: {url}")
            parts.append(
                "Tip: si el recurso está en DataStore, usa query_resource_data para paginar."
            )

        return "\n".join(parts)

import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.csv_reader import format_table, preview_csv, preview_json, preview_xlsx
from helpers.format_out import render_output
from helpers.logging import log_tool

_CSV_FORMATS = {"CSV", "TSV", "TXT", ""}
_JSON_FORMATS = {"JSON", "GEOJSON"}
_XLSX_FORMATS = {"XLSX", "XLS", "EXCEL"}


def register_preview_resource_data_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def preview_resource_data(
        resource_id: str,
        rows: int = 20,
        format: str = "text",
    ) -> str:
        """
        Download and preview a resource from Ecuador's open data portal.

        Supports CSV/TSV, JSON/GeoJSON and Excel (XLSX). Returns the first N rows
        as a formatted table so the model can inspect data without a local download.
        Geometry/WKT columns are dropped from the table (they can be tens of KB
        per cell); CSV columns in European decimal notation (7.760,2) are
        normalized to standard notation (7760.2). Max download size: 5 MB. For
        large tabular DataStore resources prefer query_resource_data.

        Args:
            resource_id: The resource UUID (get it from list_dataset_resources)
            rows: Number of data rows to preview (default: 20, max: 100)
            format: text | json
        """
        rows = min(max(rows, 1), 100)

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

        fmt = (res.get("format") or "").upper()
        name = res.get("name") or res.get("description") or "Sin título"

        try:
            if fmt == "RAR" or url.lower().endswith(".rar"):
                return render_output(
                    {
                        "error": "rar_no_soportado",
                        "url": url,
                        "resource_id": resource_id,
                    },
                    format,
                    text_builder=lambda d: (
                        "Este recurso es un archivo .rar. Todavía no lo previsualizamos como "
                        "tabla (requeriría el binario unrar como dependencia externa), pero "
                        f"puedes bajar el archivo completo con download_resource('{d['resource_id']}'), "
                        f"o directamente desde: {d['url']}"
                    ),
                )
            if fmt in _CSV_FORMATS or (
                not fmt and url.lower().endswith((".csv", ".tsv", ".txt"))
            ):
                result = await preview_csv(url, max_rows=rows)
            elif fmt in _JSON_FORMATS or url.lower().endswith((".json", ".geojson")):
                result = await preview_json(url, max_rows=rows)
            elif fmt in _XLSX_FORMATS or url.lower().endswith((".xlsx", ".xls")):
                if fmt == "XLS" or url.lower().endswith(".xls"):
                    return render_output(
                        {
                            "error": "xls_no_soportado",
                            "url": url,
                            "resource_id": resource_id,
                        },
                        format,
                        text_builder=lambda d: (
                            "Este recurso es Excel legacy (.xls), que no previsualizamos como "
                            f"tabla. Puedes bajarlo con download_resource('{d['resource_id']}') "
                            f"y abrirlo localmente, o desde: {d['url']}"
                        ),
                    )
                result = await preview_xlsx(url, max_rows=rows)
            else:
                return render_output(
                    {
                        "error": "formato_no_soportado",
                        "format_detectado": fmt or None,
                        "url": url,
                        "resource_id": resource_id,
                    },
                    format,
                    text_builder=lambda d: (
                        f"Este recurso tiene formato '{d.get('format_detectado') or 'desconocido'}'. "
                        "preview_resource_data soporta CSV/TSV, JSON/GeoJSON y XLSX. "
                        "Si está en DataStore prueba query_resource_data. "
                        f"Descarga directa: {d['url']}"
                    ),
                )
        except httpx.HTTPError as e:
            return render_output(
                {"error": f"download_failed: {e}", "url": url},
                format,
                text_builder=lambda d: f"Error al descargar el archivo: {d['error']}",
            )
        except Exception as e:
            return render_output(
                {"error": str(e)},
                format,
                text_builder=lambda d: f"Error al procesar el archivo: {d['error']}",
            )

        headers = result["headers"]
        data_rows = result["rows"]

        if not headers:
            return render_output(
                {"error": "vacio", "name": name, "resource_id": resource_id},
                format,
                text_builder=lambda d: (
                    f"El archivo '{d['name']}' está vacío o no pudo ser parseado."
                ),
            )

        payload = {
            "resource_id": resource_id,
            "name": name,
            "url": url,
            "format": result.get("format", fmt or "csv"),
            "headers": headers,
            "rows": data_rows,
            "total_rows_in_preview": result["total_rows_in_preview"],
            "truncated": result.get("truncated", False),
            "sheet": result.get("sheet"),
            "total_records": result.get("total_records"),
            "dropped_columns": result.get("dropped_columns"),
            "converted_decimal_columns": result.get("converted_decimal_columns"),
        }

        def to_text(data: dict) -> str:
            parts = [
                f"Preview de: {data['name']}",
                f"Resource ID: {data['resource_id']}",
                f"Formato: {data.get('format')}",
                f"Columnas: {len(data.get('headers') or [])}",
                f"Filas mostradas: {data['total_rows_in_preview']}",
            ]
            if data.get("sheet"):
                parts.append(f"Hoja: {data['sheet']}")
            if data.get("total_records") is not None:
                parts.append(f"Registros totales (en archivo): {data['total_records']}")
            if data.get("truncated"):
                parts.append("⚠ Archivo truncado (excede 5 MB o tiene más filas)")
            if data.get("dropped_columns"):
                parts.append(
                    "⚠ Columnas de geometría omitidas (WKT): "
                    + ", ".join(data["dropped_columns"])
                )
            if data.get("converted_decimal_columns"):
                parts.append(
                    "Columnas convertidas de formato decimal europeo (7.760,2 → 7760.2): "
                    + ", ".join(data["converted_decimal_columns"])
                )
            parts.append("")
            parts.append(format_table(data["headers"], data["rows"]))
            if data.get("truncated"):
                parts.append("")
                parts.append(f"Descarga el archivo completo: {data['url']}")
                parts.append(
                    "Tip: si el recurso está en DataStore, usa query_resource_data para paginar."
                )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)

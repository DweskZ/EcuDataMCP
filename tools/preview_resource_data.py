import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.csv_reader import (
    format_table,
    preview_csv,
    preview_json,
    preview_ods,
    preview_targz,
    preview_xls,
    preview_xlsb,
    preview_xlsx,
    preview_zip,
    sniff_content_type,
)
from helpers.format_out import render_output
from helpers.logging import log_tool

_CSV_FORMATS = {"CSV", "TSV", "TXT", ""}
_JSON_FORMATS = {"JSON", "GEOJSON"}
_XLSX_FORMATS = {"XLSX", "EXCEL"}


def classify_resource_format(fmt: str, url: str) -> str:
    """Classify a resource as RAR/TARGZ/ZIP/XLS/XLSB/XLSX/ODS/JSON/CSV/UNKNOWN.

    CKAN's declared `format` is frequently wrong (e.g. a .tar.gz or .xlsx
    file tagged "CSV" by whoever published it), so a recognizable URL
    extension always wins over a conflicting declared format. Only when
    the extension itself is not diagnostic do we fall back to `fmt`.
    """
    url_lower = url.lower()
    if url_lower.endswith(".rar"):
        return "RAR"
    if url_lower.endswith((".tar.gz", ".tgz")):
        return "TARGZ"
    if url_lower.endswith(".zip"):
        return "ZIP"
    if url_lower.endswith(".xlsx"):
        return "XLSX"
    if url_lower.endswith(".xls"):
        return "XLS"
    if url_lower.endswith(".xlsb"):
        return "XLSB"
    if url_lower.endswith(".ods"):
        return "ODS"
    if url_lower.endswith((".json", ".geojson")):
        return "JSON"
    if url_lower.endswith((".csv", ".tsv", ".txt")):
        return "CSV"

    if fmt == "RAR":
        return "RAR"
    if fmt == "ZIP":
        return "ZIP"
    if fmt == "XLS":
        return "XLS"
    if fmt == "XLSB":
        return "XLSB"
    if fmt == "ODS":
        return "ODS"
    if fmt in _XLSX_FORMATS:
        return "XLSX"
    if fmt in _JSON_FORMATS:
        return "JSON"
    if fmt in _CSV_FORMATS:
        return "CSV"
    return "UNKNOWN"


_CONTENT_TYPE_KIND = {
    "text/csv": "CSV",
    "text/plain": "CSV",
    "application/csv": "CSV",
    "application/json": "JSON",
    "application/geo+json": "JSON",
    "application/vnd.ms-excel": "XLS",
    "application/vnd.ms-excel.sheet.binary.macroenabled.12": "XLSB",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
    "application/vnd.oasis.opendocument.spreadsheet": "ODS",
    "application/zip": "ZIP",
    "application/x-zip-compressed": "ZIP",
    "application/gzip": "TARGZ",
    "application/x-gzip": "TARGZ",
    "application/x-rar-compressed": "RAR",
    "application/vnd.rar": "RAR",
}


def classify_from_content_type(content_type: str | None) -> str:
    """Map an HTTP Content-Type header to the same kind vocabulary as
    classify_resource_format. Used as a last-resort fallback for resources
    with neither a recognizable URL extension nor a useful declared format
    (e.g. a download endpoint like `/download?id=123`)."""
    if not content_type:
        return "UNKNOWN"
    mime = content_type.split(";", 1)[0].strip().lower()
    return _CONTENT_TYPE_KIND.get(mime, "UNKNOWN")


def register_preview_resource_data_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def preview_resource_data(
        resource_id: str,
        rows: int = 20,
        source: str = "nacional",
        format: str = "text",
    ) -> str:
        """
        Download and preview a resource from Ecuador's open data portal.

        Supports CSV/TSV, JSON/GeoJSON, Excel (XLS/XLSX/XLSB), OpenDocument (ODS),
        and .tar.gz/.zip archives
        that wrap a CSV/TSV/TXT file. Returns the first N rows as a formatted table
        so the model can inspect data without a local download. Geometry/WKT columns
        are dropped from the table (they can be tens of KB per cell); CSV columns
        in European decimal notation (7.760,2) are normalized to standard notation
        (7760.2). Max download size: 5 MB. For large tabular DataStore resources
        prefer query_resource_data.

        Args:
            resource_id: The resource UUID (get it from list_dataset_resources)
            rows: Number of data rows to preview (default: 20, max: 100)
            source: "nacional" (default), "cuenca" (Cuenca municipal portal), or
                    "latacunga" (Latacunga municipal portal)
            format: text | json
        """
        rows = min(max(rows, 1), 100)

        try:
            res = await ckan_client.get_resource(resource_id, source=source)
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
        kind = classify_resource_format(fmt, url)
        sniffed = False
        if kind == "UNKNOWN":
            content_type = await sniff_content_type(url)
            sniffed_kind = classify_from_content_type(content_type)
            if sniffed_kind != "UNKNOWN":
                kind = sniffed_kind
                sniffed = True

        try:
            if kind == "RAR":
                return render_output(
                    {
                        "error": "rar_no_soportado",
                        "url": url,
                        "resource_id": resource_id,
                    },
                    format,
                    text_builder=lambda d: (
                        "Este recurso es un archivo .rar. Todavía no lo previsualizamos como "
                        "tabla (requeriría una dependencia/backend externo para extracción RAR), "
                        f"pero puedes bajar el archivo completo con "
                        f"download_resource('{d['resource_id']}', format=\"json\"), "
                        f"o directamente desde: {d['url']}"
                    ),
                )
            if kind == "TARGZ":
                result = await preview_targz(url, max_rows=rows)
            elif kind == "ZIP":
                result = await preview_zip(url, max_rows=rows)
            elif kind == "XLS":
                result = await preview_xls(url, max_rows=rows)
            elif kind == "XLSB":
                result = await preview_xlsb(url, max_rows=rows)
            elif kind == "XLSX":
                result = await preview_xlsx(url, max_rows=rows)
            elif kind == "ODS":
                result = await preview_ods(url, max_rows=rows)
            elif kind == "JSON":
                result = await preview_json(url, max_rows=rows)
            elif kind == "CSV":
                result = await preview_csv(url, max_rows=rows)
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
                        "preview_resource_data soporta CSV/TSV, JSON/GeoJSON, Excel (XLS/XLSX/XLSB), "
                        "OpenDocument (ODS) y .tar.gz/.zip (si envuelven un CSV/TSV/TXT). "
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
            "member_name": result.get("member_name"),
            "total_records": result.get("total_records"),
            "dropped_columns": result.get("dropped_columns"),
            "converted_decimal_columns": result.get("converted_decimal_columns"),
            "sniffed_content_type": sniffed,
        }

        def to_text(data: dict) -> str:
            parts = [
                f"Preview de: {data['name']}",
                f"Resource ID: {data['resource_id']}",
                f"Formato: {data.get('format')}",
                f"Columnas: {len(data.get('headers') or [])}",
                f"Filas mostradas: {data['total_rows_in_preview']}",
            ]
            if data.get("sniffed_content_type"):
                parts.append(
                    "ℹ Formato detectado por Content-Type HTTP (la URL no tenía "
                    "extensión reconocible ni CKAN declaraba un formato útil)"
                )
            if data.get("sheet"):
                parts.append(f"Hoja: {data['sheet']}")
            if data.get("member_name"):
                parts.append(f"Archivo interno: {data['member_name']}")
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

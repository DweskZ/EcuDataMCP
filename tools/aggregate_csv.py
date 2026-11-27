import json
import logging
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers import csv_aggregate
from helpers.csv_reader import format_table
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.result_types import ResultadoTabla
from helpers.safe_download import UnsafeUrlError
from helpers.tool_meta import READ_ONLY

logger = logging.getLogger(__name__)


def _names(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _number(value: float) -> str:
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _filters(text: str) -> dict[str, list[str]]:
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ToolError(f"Error: filters_json no es JSON válido: {e}") from e
    if not isinstance(parsed, dict):
        raise ToolError("Error: filters_json debe ser un objeto JSON (diccionario).")
    filters: dict[str, list[str]] = {}
    for column, wanted in parsed.items():
        values = wanted if isinstance(wanted, list) else [wanted]
        if any(isinstance(v, dict | list) or v is None for v in values):
            raise ToolError(
                f"Error: el filtro de '{column}' debe ser un valor o una lista de valores."
            )
        filters[str(column)] = [str(v) for v in values]
    return filters


def register_aggregate_csv_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Sumar y agrupar un CSV completo",
        description=(
            "Group and total a CSV/TSV/TXT at a URL by reading all of it, not just "
            "its head: up to 30 MB, or a CSV inside a .zip (member) up to 2 GB "
            "unzipped. group_by, sum_columns, exact filters, ordering; reads "
            "decimal commas, pipe or semicolon delimiters and a BOM. Built for "
            "SRI's sales (sri_ventas_AAAA.csv) and RUC files."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def aggregate_csv(
        url: str,
        group_by: str = "",
        sum_columns: str = "",
        filters_json: str = "",
        order_by: str = "",
        limit: int = 50,
        skip_rows: int = 0,
        member: str = "",
        format: Literal["text", "json"] = "text",
    ) -> Annotated[CallToolResult, ResultadoTabla]:
        """
        Group the rows of a whole delimited text file and total its numeric columns.

        read_zip_member and preview_resource_data read only the first 5 MB of a
        file, so a total over a file of 5 to 30 MB would leave rows out. This
        downloads the file whole and returns one row per group: the group
        values, the number of rows (`filas`) and the total of each sum column,
        plus the totals over every matching row. Numbers are summed exactly.

        Reads plain text (.csv, .tsv, .txt, no extension); a spreadsheet goes
        through read_zip_member, and a plain file over 30 MB is refused rather
        than summed incompletely. For a CSV inside a .zip, pass the .zip as url
        and the file's name (from list_zip_contents) as member: it is
        decompressed as it is read, so a member of hundreds of MB works (the
        SRI's RUC file for Pichincha is 156 MB zipped and 740 MB of text), up
        to 300 MB zipped, 2 GB unzipped and 3 minutes of reading; a bigger one
        is refused. A host that cannot send part of a .zip is downloaded whole
        first, which adds time.

        Column names match ignoring case and accents (AÑO, año and ano are the
        same). The delimiter (comma, pipe, semicolon or tab) is read from the
        header line, and the encoding (UTF-8, with or without BOM, or Windows
        1252) from the file. Numbers may use a decimal comma ("1234,56") or a
        point; a lone comma is a decimal mark, so "1,234" reads as 1.234. Blank
        cells and cells that are not numbers are left out of the totals and
        counted in `celdas_vacias` and `celdas_no_numericas`.

        Example, SRI sales by province in 2025 (search_archivos with
        fuente="sri_datasets" and query="ventas" lists the yearly files):
        group_by="PROVINCIA", sum_columns="TOTAL_VENTAS,TOTAL_COMPRAS". Add
        filters_json='{"MES": [1, 2, 3]}' for the first quarter, or group_by=
        "MES" to see the year by month. Column names differ between years
        (VENTAS_NETAS_TARIFA_12 in 2018, VENTAS_NETAS_TARIFA_GRAVADA in 2026),
        so read the `columnas` of the answer when a name is not found.

        Args:
            url: Direct URL to a plain-text CSV/TSV/TXT file (from search_archivos or a CKAN resource), or to a .zip when member is given.
            member: File inside the .zip at url (exact name, or a unique basename); empty when url is the CSV itself.
            group_by: Comma-separated column names to group by; empty gives one total row.
            sum_columns: Comma-separated numeric columns to total; empty only counts rows.
            filters_json: Optional JSON object of exact filters, e.g. '{"PROVINCIA": "PICHINCHA", "MES": [1, 2]}'.
            order_by: Result column to sort by, optionally with asc or desc; default is the first total, biggest first.
            limit: Groups to return (default 50, max 500); the totals always cover all of them.
            skip_rows: Lines above the header line (default 0).
            format: text | json
        """
        limit = min(max(limit, 1), 500)
        group_columns = _names(group_by)
        sum_column_names = _names(sum_columns)
        filters = _filters(filters_json)

        try:
            result = await csv_aggregate.aggregate_url(
                url,
                group_by=group_columns,
                sum_columns=sum_column_names,
                filters=filters,
                order_by=order_by,
                limit=limit,
                skip_rows=max(skip_rows, 0),
                member=member,
            )
        except UnsafeUrlError as e:
            logger.warning("aggregate_csv rechazó la URL %s: %s", url, e)
            raise ToolError(
                "URL rechazada por seguridad: el destino no es público"
            ) from e
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Error al leer y agrupar el archivo: {e}") from e

        payload = {
            "url": url,
            "url_fuente": url,
            "group_by": group_columns,
            "sum_columns": sum_column_names,
            "filters": filters or None,
            **result,
        }

        def to_text(data: dict) -> str:
            parts = [
                f"Archivo: {data['url']}",
                *([f"Miembro del .zip: {data['miembro']}"] if data.get("miembro") else []),
                (
                    f"Filas leídas: {data['filas_leidas']:,} "
                    f"({data['filas_coinciden']:,} cumplen los filtros)"
                ),
                f"Grupos: {data['grupos']:,}; mostrados: {len(data['rows'])}",
                f"Delimitador: {data['delimitador']!r}; tamaño: {data['bytes_leidos']:,} bytes",
            ]
            if data.get("filters"):
                parts.append(f"Filtros: {json.dumps(data['filters'], ensure_ascii=False)}")
            for label, key in (
                ("Celdas vacías (fuera de los totales)", "celdas_vacias"),
                ("Celdas no numéricas (fuera de los totales)", "celdas_no_numericas"),
            ):
                if data.get(key):
                    parts.append(f"⚠ {label}: {json.dumps(data[key], ensure_ascii=False)}")
            if data["truncated"]:
                parts.append("⚠ Hay más grupos: sube limit o filtra con filters_json.")
            width = len(data["group_by"])
            table = [
                [
                    *row[:width],
                    f"{row[width]:,}",
                    *(_number(value) for value in row[width + 1 :]),
                ]
                for row in data["rows"]
            ]
            parts.extend(["", format_table(data["headers"], table)])
            parts.extend(["", "Totales sobre todas las filas que cumplen:"])
            parts.extend(f"- {name}: {_number(value)}" for name, value in data["totales"].items())
            parts.append("")
            parts.append("Columnas del archivo: " + ", ".join(data["columnas"]))
            return "\n".join(parts)

        return render_structured(payload, format, text_builder=to_text)

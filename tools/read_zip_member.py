import logging
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from helpers.csv_reader import format_table
from helpers.csv_reader import read_zip_member as _read_zip_member
from helpers.format_out import render_structured
from helpers.logging import log_tool
from helpers.result_types import ResultadoTabla
from helpers.safe_download import UnsafeUrlError
from helpers.tool_meta import READ_ONLY

logger = logging.getLogger(__name__)


def register_read_zip_member_tool(mcp: MCPServer) -> None:
    @mcp.tool(
        title="Leer un archivo dentro de un ZIP remoto",
        description=(
            "Read one CSV/TSV/TXT or XLSX/XLS/XLSB/ODS file inside a remote ZIP as "
            "a table, fetching only that file's bytes via HTTP Range. Get member "
            "names from list_zip_contents first. Max 5 MB compressed per member. "
            "Detects the header below a report's title block."
        ),
        annotations=READ_ONLY,
    )
    @log_tool
    async def read_zip_member(
        url: str,
        member: str,
        rows: int = 50,
        offset: int = 0,
        skip_rows: int = -1,
        format: Literal["text", "json"] = "text",
    ) -> Annotated[CallToolResult, ResultadoTabla]:
        """
        Read the rows of ONE file inside a remote .zip archive, without
        downloading the archive.

        Run list_zip_contents first to get the member's exact name. This tool
        reads the archive's central directory, then fetches only that
        member's local header and compressed bytes via HTTP Range requests,
        so it works inside archives far larger than the 5 MB cap of
        preview_resource_data/download_resource (e.g. INEC's tabulados ZIPs).

        Limits:
        - The server must honor HTTP Range (answer 206); otherwise it fails
          with a clear error.
        - The member must be at most 5 MB compressed. CSV/TSV/TXT output stops
          at 5 MB decompressed (marked truncated); spreadsheets must fit in
          20 MB decompressed, since they can't be opened partially.
        - Only stored or deflate members; no encrypted members. ZIP64
          archives are supported.
        - Supported formats: .csv, .tsv, .txt, .xlsx, .xls, .xlsb, .ods (first
          sheet). The CRC32 is checked whenever the member is read in full.

        Matching: exact name first, then a unique case-insensitive or
        basename match; otherwise the error suggests close names.

        Report tables: statistical tabulados (INEC, BCE) open with a title
        block (table number, indicator, population, source) above the
        column header. By default the header is detected as the first row
        at least half as full as the fullest of the first 30 rows; the
        rows above it come back as `preamble` and their count as
        `header_row`. Set skip_rows to 0 to keep row 1 as the header, or to
        n to skip exactly n rows. Lines the source quoted whole are split
        back into fields, and columns empty in every row are dropped.

        Args:
            url: Direct URL to a .zip file (the same URL given to list_zip_contents).
            member: Member path inside the zip, as listed by list_zip_contents.
            rows: Data rows to return (default 50, max 500).
            offset: Data rows to skip before returning, for pagination.
            skip_rows: Rows above the column header; -1 (default) detects them, 0 keeps row 1.
            format: text | json
        """
        rows = min(max(rows, 1), 500)
        offset = max(offset, 0)

        try:
            result = await _read_zip_member(
                url, member, max_rows=offset + rows, skip_rows=skip_rows
            )
        except UnsafeUrlError as e:
            # The guard's message names the resolved private IP: keep that
            # detail in the server log, never in the client-facing error.
            logger.warning("read_zip_member rechazó la URL %s: %s", url, e)
            raise ToolError(
                "URL rechazada por seguridad: el destino no es público"
            ) from e
        except ValueError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            raise ToolError(f"Error al leer el archivo dentro del .zip: {e}") from e

        page = result["rows"][offset : offset + rows]
        payload = {
            "url": url,
            "member_name": result["member_name"],
            "format": result.get("format"),
            "compressed_size": result["compressed_size"],
            "uncompressed_size": result["uncompressed_size"],
            "headers": result["headers"],
            "rows": page,
            "offset": offset,
            "total_rows_in_preview": len(page),
            "truncated": result.get("truncated", False),
            "sheet": result.get("sheet"),
            "dropped_columns": result.get("dropped_columns"),
            "converted_decimal_columns": result.get("converted_decimal_columns"),
            "header_row": result.get("header_row", 0),
            "preamble": result.get("preamble") or [],
            "dropped_empty_columns": result.get("dropped_empty_columns", 0),
        }

        def to_text(data: dict) -> str:
            parts = [
                f"Archivo interno: {data['member_name']}",
                f"ZIP: {data['url']}",
                f"Formato: {data.get('format')}",
                f"Columnas: {len(data.get('headers') or [])}",
                f"Filas mostradas: {data['total_rows_in_preview']} desde offset={data['offset']}",
            ]
            if data.get("sheet"):
                parts.append(f"Hoja: {data['sheet']}")
            if data.get("preamble"):
                parts.append(
                    f"Encabezado detectado en la fila {data['header_row'] + 1}; "
                    "filas de título:"
                )
                parts.extend(f"  {line}" for line in data["preamble"])
            if data.get("dropped_empty_columns"):
                parts.append(
                    f"Columnas vacías omitidas: {data['dropped_empty_columns']}"
                )
            if data.get("truncated"):
                parts.append(
                    "⚠ Hay más filas: sube offset para paginar (o el archivo pasa de 5 MB)"
                )
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
            if not data["headers"]:
                parts.append("El archivo está vacío.")
            else:
                parts.append(format_table(data["headers"], data["rows"]))
            return "\n".join(parts)

        return render_structured(payload, format, text_builder=to_text)

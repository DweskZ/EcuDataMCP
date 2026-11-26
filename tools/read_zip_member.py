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
            "a table, fetching only that file's bytes via HTTP Range (a CSV is read "
            "from its first 5 MB; for totals over a whole CSV use aggregate_csv); "
            "any sheet, a zip inside the zip (inner_member), or with member='' a "
            "spreadsheet published at the URL itself. Names from list_zip_contents."
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
        sheet: str = "",
        inner_member: str = "",
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
        - CSV/TSV/TXT members of any size are read from their first bytes: the
          output stops at 5 MB decompressed and is marked truncated, and no
          more than 5 MB of the member is downloaded (a 400 MB microdata CSV
          previews in seconds). Spreadsheets can't be opened partially, so
          they must fit in 20 MB both compressed and decompressed.
        - Only stored or deflate members; no encrypted members. ZIP64
          archives are supported.
        - Supported formats: .csv, .tsv, .txt, .xlsx, .xls, .xlsb, .ods. The
          CRC32 is checked whenever the member is read in full.

        Sheets: spreadsheets open on their active (usually first) sheet; pass
        sheet as a name or a 1-based number for another one. A name wins over
        a number, so a sheet called "2024" is read by that name. The result
        lists every sheet of the workbook in `sheets`, and a wrong name fails
        with that list.

        Zip inside a zip: INEC publishes its CSV tabulados as a .zip of .zip
        files. When `member` is itself a .zip (at most 20 MB compressed and
        20 MB expanded), pass the file to read inside it as inner_member;
        leaving inner_member empty fails with the inner file names. A text
        file inside is cut at 5 MB like any other.

        Files outside a zip: with member='' the URL itself is read as a
        spreadsheet or text file (e.g. SIPA's precios-agroindustria.xlsx),
        downloaded whole up to 20 MB for spreadsheets and 5 MB for text.

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
            sheet: Spreadsheet sheet name or 1-based number; empty reads the active sheet.
            inner_member: File to read inside a .zip member; only when member is a .zip.
            format: text | json
        """
        rows = min(max(rows, 1), 500)
        offset = max(offset, 0)

        try:
            result = await _read_zip_member(
                url,
                member,
                max_rows=offset + rows,
                skip_rows=skip_rows,
                sheet=sheet,
                inner_member=inner_member,
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
            "sheets": result.get("sheets") or [],
            "dropped_columns": result.get("dropped_columns"),
            "converted_decimal_columns": result.get("converted_decimal_columns"),
            "header_row": result.get("header_row", 0),
            "preamble": result.get("preamble") or [],
            "dropped_empty_columns": result.get("dropped_empty_columns", 0),
        }
        if result.get("outer_member"):
            payload["outer_member"] = result["outer_member"]

        def to_text(data: dict) -> str:
            parts = [
                f"Archivo interno: {data['member_name']}",
                f"URL: {data['url']}",
                f"Formato: {data.get('format')}",
                f"Columnas: {len(data.get('headers') or [])}",
                f"Filas mostradas: {data['total_rows_in_preview']} desde offset={data['offset']}",
            ]
            if data.get("sheet"):
                parts.append(f"Hoja: {data['sheet']}")
            if len(data.get("sheets") or []) > 1:
                parts.append(
                    "Hojas del libro: "
                    + "; ".join(f"{i + 1}. {n}" for i, n in enumerate(data["sheets"]))
                )
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

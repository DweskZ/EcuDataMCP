import csv
import io
import logging
from typing import Any

import httpx

from helpers.logging import MAIN_LOGGER_NAME
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
_TIMEOUT = 30.0


async def preview_csv(
    url: str, max_rows: int = 20, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """
    Download a CSV file and return the first N rows parsed.

    Returns:
        dict with 'headers', 'rows', 'total_rows_in_preview', 'truncated'
    """
    own = session is None
    if own:
        session = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
    assert session is not None
    try:
        logger.debug("Downloading CSV from %s (max %d bytes)", url, MAX_DOWNLOAD_BYTES)
        async with session.stream("GET", url, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()

            content_length = resp.headers.get("content-length")
            if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                truncated = True
            else:
                truncated = False

            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                chunks.append(chunk)
                total += len(chunk)
                if total >= MAX_DOWNLOAD_BYTES:
                    truncated = True
                    break

        raw = b"".join(chunks)

        # Strip UTF-8 BOM if present
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]

        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                text = raw.decode(encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            text = raw.decode("utf-8", errors="replace")

        # Detect delimiter
        sample = text[:2000]
        delimiter = ","
        for candidate in (";", "\t", "|"):
            if sample.count(candidate) > sample.count(delimiter):
                delimiter = candidate

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows_read: list[list[str]] = []
        for row in reader:
            rows_read.append(row)
            if len(rows_read) > max_rows + 1:
                truncated = True
                break

        if not rows_read:
            return {"headers": [], "rows": [], "total_rows_in_preview": 0, "truncated": False}

        headers = rows_read[0]
        data_rows = rows_read[1 : max_rows + 1]

        return {
            "headers": headers,
            "rows": data_rows,
            "total_rows_in_preview": len(data_rows),
            "truncated": truncated,
        }
    finally:
        if own:
            await session.aclose()


def format_table(headers: list[str], rows: list[list[str]], max_col_width: int = 40) -> str:
    """Format headers and rows as a readable text table."""
    if not headers:
        return "No data available."

    def trunc(val: str) -> str:
        val = val.strip()
        return val[:max_col_width] + "..." if len(val) > max_col_width else val

    display_headers = [trunc(h) for h in headers]
    display_rows = [[trunc(cell) for cell in row] for row in rows]

    ncols = len(display_headers)
    for row in display_rows:
        while len(row) < ncols:
            row.append("")

    col_widths = [len(h) for h in display_headers]
    for row in display_rows:
        for i, cell in enumerate(row[:ncols]):
            col_widths[i] = max(col_widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return " | ".join(
            cell.ljust(col_widths[i]) for i, cell in enumerate(cells[:ncols])
        )

    lines = [fmt_row(display_headers)]
    lines.append("-+-".join("-" * w for w in col_widths))
    for row in display_rows:
        lines.append(fmt_row(row))

    return "\n".join(lines)

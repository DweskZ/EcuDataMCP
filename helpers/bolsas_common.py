"""Shared plumbing for the two stock-exchange clients
(helpers/bvg_client.py, helpers/bvq_client.py).

Both sites publish their historical data as plain XLSX/XLS links on ordinary
HTML pages, so each client scrapes a page and lists the links. What the pages
do not say is how fresh each file is, which matters here: the exchanges
overwrite the same file in place (`BVG_Acciones.xlsx` is rebuilt every
trading day), so the only freshness signal is the HTTP `Last-Modified` header.
`probe_archivos` reads it with a one-byte ranged GET per file (the BVQ host
answers HEAD with an empty reply, so HEAD is not an option) and never
downloads a file body.
"""

from __future__ import annotations

import asyncio
import logging
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from helpers.csv_reader import _fetch_range, download_bytes
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_KNOWN_FORMATS = {"XLSX", "XLS", "CSV", "PDF", "ZIP"}
_PROBE_CONCURRENCY = 6


def formato_from_url(url: str) -> str:
    name = url.split("?", 1)[0].rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].upper() if "." in name else ""
    return ext if ext in _KNOWN_FORMATS else "DESCONOCIDO"


async def fetch_html(url: str) -> str:
    """Download a page and decode it as UTF-8 (both sites serve UTF-8),
    falling back to cp1252 so a legacy page still yields readable labels."""
    content, truncated = await download_bytes(url)
    if truncated:
        raise ValueError(f"La página de {url} superó el límite de descarga.")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def _parse_last_modified(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return None


def _total_size(headers: httpx.Headers) -> int | None:
    content_range = headers.get("content-range", "")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[-1].strip()
        if total.isdigit():
            return int(total)
    length = headers.get("content-length", "")
    return int(length) if length.isdigit() else None


async def probe_archivos(archivos: list[dict[str, Any]]) -> None:
    """Add `modificado` (ISO-8601 UTC from Last-Modified) and `tamano_bytes`
    to each file in place. A file whose probe fails keeps both as None: the
    listing is still useful without them."""
    sem = asyncio.Semaphore(_PROBE_CONCURRENCY)

    async def probe(archivo: dict[str, Any]) -> None:
        archivo.setdefault("modificado", None)
        archivo.setdefault("tamano_bytes", None)
        async with sem:
            try:
                _, headers, _ = await _fetch_range(archivo["url"], "bytes=0-0", 1)
            except Exception as exc:
                logger.warning("Sin cabeceras de %s: %r", archivo["url"], exc)
                return
        archivo["modificado"] = _parse_last_modified(headers.get("last-modified"))
        archivo["tamano_bytes"] = _total_size(headers)

    await asyncio.gather(*(probe(a) for a in archivos))

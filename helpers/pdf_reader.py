import io
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

# download_bytes/MAX_DOWNLOAD_BYTES are format-agnostic (SSRF-guarded,
# TLS-fallback, size-capped) despite living in csv_reader.py -- every other
# non-tabular download in this project (xls/xlsx/ods/zip/tar.gz previews)
# reuses them the same way rather than duplicating the download logic here.
from helpers.csv_reader import download_bytes, sniff_content_type

MAX_PAGES_PER_CALL = 20

_PAGE_RANGE_RE = re.compile(r"(\d+)(?:-(\d+))?")

# Known-large/non-PDF formats seen in the wild pointed at this tool by
# mistake (survey microdata ZIPs, tabulados XLSX...) -- rejecting on
# extension avoids burning a doomed 5 MB partial download before pypdf
# would fail on it anyway.
_NON_PDF_EXTENSIONS = (
    ".zip", ".tar.gz", ".tgz", ".rar", ".7z",
    ".xlsx", ".xls", ".csv", ".docx", ".doc",
)


def _parse_pages(pages: str, total_pages: int) -> tuple[list[int], bool]:
    """Parse a 1-indexed page spec ("3", "1-5", "1,4,9") into a sorted list
    of 0-indexed page numbers. Empty spec means "the whole document".
    Returns (selected, was_capped) -- was_capped is True when the spec (or
    the whole document) matched more than MAX_PAGES_PER_CALL pages, so the
    caller can tell the model to ask again with a narrower range."""
    if not pages.strip():
        matched = list(range(total_pages))
    else:
        indices: set[int] = set()
        for part in pages.split(","):
            part = part.strip()
            if not part:
                continue
            match = _PAGE_RANGE_RE.fullmatch(part)
            if not match:
                raise ValueError(
                    f"Rango de páginas inválido: {part!r}. Usa formatos como "
                    "'3', '1-5' o '1,3,7' (1-indexado)."
                )
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            if start < 1 or end < start:
                raise ValueError(f"Rango de páginas inválido: {part!r}.")
            for p in range(start, end + 1):
                if 1 <= p <= total_pages:
                    indices.add(p - 1)
        matched = sorted(indices)

    was_capped = len(matched) > MAX_PAGES_PER_CALL
    return matched[:MAX_PAGES_PER_CALL], was_capped


def extract_text_from_bytes(raw: bytes, pages: str = "") -> dict[str, Any]:
    """Extract text from already-downloaded PDF bytes. Shared by `read_pdf`
    (URL-based) and any caller that fetches PDF bytes through a mechanism
    `download_bytes` can't express (e.g. a session-bound POST download with
    no stable URL) -- `pages` has the same 1-indexed range-spec semantics as
    `read_pdf`, capped at MAX_PAGES_PER_CALL pages per call either way.
    """
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError, PyPdfError

    try:
        reader = PdfReader(io.BytesIO(raw))
    except PdfReadError as e:
        raise ValueError(
            "El archivo no se pudo leer como PDF: está corrupto o no es un "
            "PDF válido."
        ) from e

    if reader.is_encrypted:
        # Empty-password PDFs (encrypted only to restrict printing/editing,
        # not to hide content) still decrypt with "" -- try that before
        # giving up, same as most PDF viewers do transparently.
        try:
            reader.decrypt("")
        except (PyPdfError, NotImplementedError):
            pass
    if reader.is_encrypted:
        raise ValueError(
            "Este PDF está protegido con contraseña; no se puede leer sin ella."
        )

    total_pages = len(reader.pages)
    if total_pages == 0:
        return {"total_pages": 0, "pages": [], "pages_capped": False}

    selected, pages_capped = _parse_pages(pages, total_pages)

    page_results = [
        {"page": idx + 1, "text": (reader.pages[idx].extract_text() or "").strip()}
        for idx in selected
    ]

    return {
        "total_pages": total_pages,
        "pages": page_results,
        "pages_capped": pages_capped,
    }


async def read_pdf(
    url: str, pages: str = "", session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Extract text from a PDF at `url`. `pages` is a 1-indexed range spec
    ("3", "1-5", "1,4,9"); empty means the whole document, capped at
    MAX_PAGES_PER_CALL pages per call either way.
    """
    path = urlsplit(url).path.lower()
    if path.endswith(_NON_PDF_EXTENSIONS):
        ext = path.rsplit(".", 1)[-1]
        raise ValueError(
            f"La URL termina en .{ext}, no en .pdf -- read_pdf solo lee PDFs. "
            "Si el archivo viene de un recurso CKAN, prueba download_resource "
            "o preview_resource_data; si no, descárgalo directamente desde el enlace."
        )
    if not path.endswith(".pdf"):
        # No recognizable extension either way (e.g. a query-string-only
        # URL) -- same priority order as csv_reader's format detection:
        # URL extension first, Content-Type sniff only when that's
        # inconclusive, cheap because it only reads headers.
        content_type = await sniff_content_type(url, session=session)
        if content_type and "pdf" not in content_type.lower():
            raise ValueError(
                f"La URL no parece ser un PDF (Content-Type: {content_type}); "
                "read_pdf solo lee PDFs."
            )

    raw, truncated = await download_bytes(url, session=session)
    if truncated:
        # A PDF's xref table and trailer live at the end of the file (same
        # structural issue as .zip), so a download cut off at
        # MAX_DOWNLOAD_BYTES can't be parsed at all -- confirmed against a
        # real 14.6 MB IESS actuarial-study PDF: pypdf fails even in
        # non-strict mode ("Stream has ended unexpectedly"), not just a
        # missing-EOF warning. Skip the doomed parse and say what happened.
        raise ValueError(
            "El archivo PDF supera el límite de 5 MB de este tool, así que "
            "se descargó incompleto y no se puede leer (la tabla de "
            "referencias de un PDF vive al final del archivo). Prueba "
            "download_resource si el PDF viene de un recurso CKAN, o el "
            "enlace directo."
        )

    return extract_text_from_bytes(raw, pages=pages)

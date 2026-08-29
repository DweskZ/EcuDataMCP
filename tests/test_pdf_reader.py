import socket

import pytest

from helpers.csv_reader import MAX_DOWNLOAD_BYTES
from helpers.pdf_reader import MAX_PAGES_PER_CALL, _parse_pages, read_pdf


def _make_pdf(pages_text: list[str]) -> bytes:
    """Build a real, multi-page PDF with genuine extractable text."""
    from fpdf import FPDF

    pdf = FPDF()
    for text in pages_text:
        pdf.add_page()
        pdf.set_font("Helvetica", size=14)
        pdf.cell(0, 10, text)
    return bytes(pdf.output())


def _fake_dns(monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


# -- _parse_pages --------------------------------------------------------


def test_parse_pages_empty_spec_returns_whole_document():
    selected, capped = _parse_pages("", total_pages=5)
    assert selected == [0, 1, 2, 3, 4]
    assert capped is False


def test_parse_pages_single_page():
    selected, _capped = _parse_pages("3", total_pages=10)
    assert selected == [2]


def test_parse_pages_range():
    selected, _capped = _parse_pages("2-4", total_pages=10)
    assert selected == [1, 2, 3]


def test_parse_pages_comma_list_dedupes_and_sorts():
    selected, _capped = _parse_pages("5,1,3,1", total_pages=10)
    assert selected == [0, 2, 4]


def test_parse_pages_clamps_out_of_range_values():
    # Real portals return documents of varying length; a caller guessing at
    # a range shouldn't get an error just for asking past the last page.
    selected, _capped = _parse_pages("8-20", total_pages=10)
    assert selected == [7, 8, 9]


def test_parse_pages_rejects_malformed_spec():
    with pytest.raises(ValueError, match="Rango de páginas inválido"):
        _parse_pages("abc", total_pages=10)


def test_parse_pages_rejects_backwards_range():
    with pytest.raises(ValueError, match="Rango de páginas inválido"):
        _parse_pages("5-2", total_pages=10)


def test_parse_pages_caps_at_max_per_call():
    selected, capped = _parse_pages("", total_pages=50)
    assert len(selected) == MAX_PAGES_PER_CALL
    assert capped is True


# -- read_pdf -------------------------------------------------------------


async def test_read_pdf_extracts_text_per_page(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    raw = _make_pdf(["Primera pagina", "Segunda pagina"])
    url = "https://example.com/boletin.pdf"
    httpx_mock.add_response(url=url, content=raw)

    result = await read_pdf(url)

    assert result["total_pages"] == 2
    assert result["pages"] == [
        {"page": 1, "text": "Primera pagina"},
        {"page": 2, "text": "Segunda pagina"},
    ]
    assert result["pages_capped"] is False


async def test_read_pdf_respects_page_range(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    raw = _make_pdf([f"Pagina {i}" for i in range(1, 6)])
    url = "https://example.com/multi.pdf"
    httpx_mock.add_response(url=url, content=raw)

    result = await read_pdf(url, pages="2-3")

    assert [p["page"] for p in result["pages"]] == [2, 3]
    assert result["pages"][0]["text"] == "Pagina 2"


async def test_read_pdf_flags_pages_capped_for_long_documents(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    raw = _make_pdf([f"Pagina {i}" for i in range(1, 26)])  # 25 pages
    url = "https://example.com/largo.pdf"
    httpx_mock.add_response(url=url, content=raw)

    result = await read_pdf(url)

    assert result["total_pages"] == 25
    assert len(result["pages"]) == MAX_PAGES_PER_CALL
    assert result["pages_capped"] is True


async def test_read_pdf_over_5mb_gives_actionable_truncation_message(httpx_mock, monkeypatch):
    # Confirmed against a real 14.6 MB IESS actuarial-study PDF: a download
    # cut off at MAX_DOWNLOAD_BYTES can't be parsed at all, even in pypdf's
    # non-strict mode ("Stream has ended unexpectedly") -- a PDF's xref
    # table lives at the end of the file, same structural issue as .zip.
    _fake_dns(monkeypatch)
    real_pdf = _make_pdf(["Contenido"])
    padding = b"\x00" * (MAX_DOWNLOAD_BYTES + 10)
    url = "https://example.com/enorme.pdf"
    httpx_mock.add_response(url=url, content=real_pdf + padding)

    with pytest.raises(ValueError, match="supera el límite de 5 MB"):
        await read_pdf(url)


async def test_read_pdf_rejects_corrupt_file(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    url = "https://example.com/no_es_pdf.pdf"
    httpx_mock.add_response(url=url, content=b"not actually a pdf")

    with pytest.raises(ValueError, match="no se pudo leer como PDF"):
        await read_pdf(url)


async def test_read_pdf_empty_document_returns_no_pages(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    buf = io.BytesIO()
    writer.write(buf)
    url = "https://example.com/vacio.pdf"
    httpx_mock.add_response(url=url, content=buf.getvalue())

    result = await read_pdf(url)

    assert result["total_pages"] == 0
    assert result["pages"] == []

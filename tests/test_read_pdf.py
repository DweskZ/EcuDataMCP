import json
import socket

from mcp.server.fastmcp import FastMCP

from tools.read_pdf import register_read_pdf_tool


def _make_tool():
    mcp = FastMCP("test")
    register_read_pdf_tool(mcp)
    return mcp._tool_manager.get_tool("read_pdf").fn


def _fake_dns(monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


def _make_pdf(pages_text: list[str]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    for text in pages_text:
        pdf.add_page()
        pdf.set_font("Helvetica", size=14)
        pdf.cell(0, 10, text)
    return bytes(pdf.output())


async def test_read_pdf_returns_page_text_as_json(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    raw = _make_pdf(["Reglamento articulo 1", "Reglamento articulo 2"])
    url = "https://example.com/reglamento.pdf"
    httpx_mock.add_response(url=url, content=raw)

    tool = _make_tool()
    result = await tool(url=url, format="json")
    payload = json.loads(result)

    assert payload["total_pages"] == 2
    assert payload["pages"][0]["text"] == "Reglamento articulo 1"
    assert payload["truncated"] is False
    assert payload["pages_capped"] is False


async def test_read_pdf_text_format_includes_page_markers(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    raw = _make_pdf(["Contenido de prueba"])
    url = "https://example.com/doc.pdf"
    httpx_mock.add_response(url=url, content=raw)

    tool = _make_tool()
    result = await tool(url=url, format="text")

    assert "Página 1" in result
    assert "Contenido de prueba" in result


async def test_read_pdf_invalid_page_range_returns_actionable_error(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    raw = _make_pdf(["Una pagina"])
    url = "https://example.com/x.pdf"
    httpx_mock.add_response(url=url, content=raw)

    tool = _make_tool()
    result = await tool(url=url, pages="abc", format="json")
    payload = json.loads(result)

    assert "Rango de páginas inválido" in payload["error"]


async def test_read_pdf_corrupt_file_returns_actionable_error(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    url = "https://example.com/corrupto.pdf"
    httpx_mock.add_response(url=url, content=b"esto no es un pdf")

    tool = _make_tool()
    result = await tool(url=url, format="json")
    payload = json.loads(result)

    assert "no se pudo leer como PDF" in payload["error"]


async def test_read_pdf_no_extractable_text_gives_ocr_hint(httpx_mock, monkeypatch):
    _fake_dns(monkeypatch)
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    url = "https://example.com/escaneo.pdf"
    httpx_mock.add_response(url=url, content=buf.getvalue())

    tool = _make_tool()
    result = await tool(url=url, format="json")
    payload = json.loads(result)

    assert payload["error"] == "sin_texto_extraible"

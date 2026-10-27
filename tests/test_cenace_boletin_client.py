import gzip
import io
import json

import openpyxl
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import cenace_boletin_client as client
from tools.get_cenace_boletin import register_get_cenace_boletin_tool

_BOOK = "https://online.fliphtml5.com/htwhr/{}/"
_TITLE = "BOLETÍN Y ESTADÍSTICA MENSUAL DE TRANSACCIONES COMERCIALES - {}"


def _index_xlsx(rows: list[tuple]) -> bytes:
    """The index as CENACE ships it: a URL | NOMBRE header, then one row per
    issue, newest first, with empty trailing rows."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(("URL", "NOMBRE"))
    for row in rows:
        ws.append(row)
    ws.append((None, None))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


_INDEX = _index_xlsx(
    [
        (_BOOK.format("kffn"), _TITLE.format("JULIO 2026")),
        ("https://online.fliphtml5.com/htwhr/kwyo", _TITLE.format("JUNIO 2026")),
        (_BOOK.format("bhbg"), _TITLE.format("ENERO 2019")),
        ("https://example.com/otro/", _TITLE.format("MAYO 2026")),
        (_BOOK.format("zzzz"), "BOLETÍN SIN FECHA"),
    ]
)


def _search_config(pages: list[str]) -> str:
    return f"var textForPages ={json.dumps(pages)}; var positionForPages = [];"


@pytest.fixture(autouse=True)
def clear_cache():
    client._index_cache.clear()
    client._text_cache.clear()
    yield
    client._index_cache.clear()
    client._text_cache.clear()


async def test_list_boletines_parses_months_and_drops_bad_rows(httpx_mock):
    httpx_mock.add_response(url=client._INDEX_URL, content=_INDEX)

    result = await client.list_boletines()

    assert [(b["mes"], b["codigo"]) for b in result["boletines"]] == [
        ("2026-07", "kffn"),
        ("2026-06", "kwyo"),
        ("2019-01", "bhbg"),
    ]
    assert result["boletines"][1]["url"] == _BOOK.format("kwyo")


async def test_list_boletines_filters_by_year(httpx_mock):
    httpx_mock.add_response(url=client._INDEX_URL, content=_INDEX)

    result = await client.list_boletines(2019)

    assert [b["mes"] for b in result["boletines"]] == ["2019-01"]


async def test_get_boletin_ultimo_returns_page_texts(httpx_mock):
    httpx_mock.add_response(url=client._INDEX_URL, content=_INDEX)
    httpx_mock.add_response(
        url=f"{_BOOK.format('kffn')}files/search/search_config.js",
        text=_search_config(["\r\n\r\nPORTADA ", "CNEL GUAYAQUIL 3 036.06 39.1%\r\nQUITO  "]),
    )

    result = await client.get_boletin("ultimo")

    assert result["mes"] == "2026-07"
    assert result["paginas"] == [
        {"pagina": 1, "texto": "PORTADA"},
        {"pagina": 2, "texto": "CNEL GUAYAQUIL 3 036.06 39.1%\nQUITO"},
    ]


async def test_get_boletin_handles_double_gzip_with_bom(httpx_mock):
    httpx_mock.add_response(url=client._INDEX_URL, content=_INDEX)
    body = gzip.compress(("﻿" + _search_config(["ENERO 2019        PRODUCCIÓN"])).encode())
    httpx_mock.add_response(
        url=f"{_BOOK.format('bhbg')}files/search/search_config.js", content=body
    )

    result = await client.get_boletin("2019-01")

    assert result["paginas"][0]["texto"] == "ENERO 2019  PRODUCCIÓN"


async def test_get_boletin_rejects_missing_month(httpx_mock):
    httpx_mock.add_response(url=client._INDEX_URL, content=_INDEX)

    with pytest.raises(ValueError, match="entre 2019-01 y 2026-07"):
        await client.get_boletin("2018-05")


def test_parse_pages_requires_text_index():
    with pytest.raises(ValueError, match="textForPages"):
        client._parse_pages(b"var otraCosa = [];")


async def test_tool_lists_then_reads_one_issue(httpx_mock):
    httpx_mock.add_response(url=client._INDEX_URL, content=_INDEX)
    httpx_mock.add_response(
        url=f"{_BOOK.format('kwyo')}files/search/search_config.js",
        text=_search_config(["PORTADA", "DEMANDA"]),
    )
    server = MCPServer("test")
    register_get_cenace_boletin_tool(server)

    listed = await server.call_tool("get_cenace_boletin", {})
    assert "- 2026-06: " in listed.content[0].text

    got = await server.call_tool("get_cenace_boletin", {"mes": "2026-06"})
    assert "--- Página 2 de 2 ---\nDEMANDA" in got.content[0].text

    with pytest.raises(ToolError, match="No hay boletín"):
        await server.call_tool("get_cenace_boletin", {"mes": "2001-01"})

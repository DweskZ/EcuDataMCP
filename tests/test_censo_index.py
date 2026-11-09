"""Census tabulados index: workbook extraction, build limits, runtime search."""

import hashlib
import io
import json
import logging

import httpx
import openpyxl
import pytest

from helpers import censo_client, censo_index, censo_index_build
from tests.test_censo_client import _mock_pages


def _workbook() -> bytes:
    """A tabulado shaped like the live ones: Índice sheet + one sheet per table."""
    wb = openpyxl.Workbook()
    idx = wb.active
    idx.title = "Índice"
    idx["A4"] = "Dificultades funcionales"
    idx["A6"], idx["B6"] = "Tabla.N°", "Contenido"
    idx["A7"], idx["B7"] = "1", "Población por esfera, según provincia y área de residencia"
    idx["A8"], idx["B8"] = "1.2", "Población por esfera, según provincia, cantón y parroquia"
    for name, title, geo in (
        ("1", "Población por esfera de funcionamiento, según provincia y área de residencia", "Provincia y área"),
        ("1.2", "Población por esfera de funcionamiento, según provincia, cantón y parroquia", "Provincia, cantón y parroquia"),
    ):
        ws = wb.create_sheet(name)
        ws["A3"], ws["B3"] = "Tabla N°:", name
        ws["A4"], ws["B4"] = "Nombre de la tabla:", title
        ws["A5"], ws["B5"] = "Fuente:", "VIII Censo"
        ws["A9"], ws["B9"], ws["C9"] = "Índice", geo, "Número total de personas"
        ws["D9"] = "Esfera de funcionamiento"
        ws["D10"], ws["E10"] = "Caminar o subir gradas", "Ver, aun usando lentes"
        ws["A12"], ws["B12"], ws["C12"] = "Total Nacional", "Total Nacional", 16938986
        ws["D12"] = 12345
    # A sheet without its own title row falls back to the Índice listing.
    wb.create_sheet("9")["A1"] = "sin metadatos"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_extract_reads_titles_levels_and_column_headers():
    sheets = censo_index_build.extract_workbook_index(_workbook())

    assert [s["hoja"] for s in sheets] == ["1", "1.2", "9"]
    first, second, orphan = sheets
    assert first["titulo"].startswith("Población por esfera de funcionamiento")
    assert first["niveles"] == ["provincia"]
    assert second["niveles"] == ["provincia", "cantón", "parroquia"]
    assert "Ver, aun usando lentes" in first["columnas"]
    assert "Esfera de funcionamiento" in first["columnas"]
    assert not any(c.isdigit() for c in first["columnas"])  # data rows are not headers
    assert orphan["titulo"] == ""


def test_title_falls_back_to_the_indice_sheet():
    wb = openpyxl.Workbook()
    wb.active.title = "Índice"
    wb.active["A7"], wb.active["B7"] = "3", "Hogares por agua, según cantón"
    wb.create_sheet("3")["A1"] = "x"
    buf = io.BytesIO()
    wb.save(buf)

    (sheet,) = censo_index_build.extract_workbook_index(buf.getvalue())
    assert sheet["titulo"] == "Hogares por agua, según cantón"
    assert sheet["niveles"] == ["cantón"]


def test_file_entry_records_checksum_size_and_date():
    raw = _workbook()
    entry = censo_index_build.file_entry(
        {"url": "https://x/y.xlsx", "label": "Dificultades – Excel", "format": "XLSX", "tema": "poblacion"},
        raw,
        "2026-11-08",
    )
    assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
    assert entry["bytes"] == len(raw)
    assert entry["extraido"] == "2026-11-08"
    assert entry["niveles"] == ["provincia", "cantón", "parroquia"]
    assert entry["tema"] == "poblacion"


@pytest.mark.asyncio
async def test_build_skips_and_logs_oversized_workbooks(monkeypatch, caplog):
    from helpers import csv_reader

    resources = [
        {"url": "https://x/small.xlsx", "label": "Chico – Excel", "format": "XLSX", "tipo": "tabulado", "tema": "hogar"},
        {"url": "https://x/huge.xlsx", "label": "Enorme – Excel", "format": "XLSX", "tipo": "tabulado"},
        {"url": "https://x/data.zip", "label": "CSV", "format": "ZIP", "tipo": "microdatos"},
    ]

    async def fake_live():
        return resources

    seen_limits = []

    async def fake_download(url, session=None, *, max_bytes=0, **kw):
        seen_limits.append(max_bytes)
        return (b"x" * 10, True) if "huge" in url else (_workbook(), False)

    monkeypatch.setattr(censo_client, "fetch_live_resources", fake_live)
    monkeypatch.setattr(csv_reader, "download_bytes", fake_download)

    with caplog.at_level(logging.WARNING, logger="ecuador_mcp.censo_index_build"):
        index = await censo_index_build.build_index(max_mb=2)

    assert [f["label"] for f in index["archivos"]] == ["Chico – Excel"]
    assert index["omitidos"][0]["url"] == "https://x/huge.xlsx"
    assert "2 MB" in index["omitidos"][0]["motivo"]
    assert seen_limits == [2 * 1024 * 1024] * 2  # bounded download, never the 5 MB default
    assert "Skipping https://x/huge.xlsx" in caplog.text


def test_committed_index_loads_and_has_the_ict_tabulado():
    index = censo_index.load_index()
    assert index["archivos"], "run scripts/build_censo_index.py"
    assert all(f["sha256"] and f["extraido"] and f["url"].startswith("https://") for f in index["archivos"])
    assert index["omitidos"] == [] or all("motivo" in o for o in index["omitidos"])
    ict = next(f for f in index["archivos"] if "03_2022_CPV_TIC" in f["url"])
    text = " ".join(censo_index.sheet_text(h) for h in ict["hojas"])
    assert "internet" in text and "computadora" in text
    assert "parroquia" in ict["niveles"]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["internet", "computadora"])
async def test_search_finds_the_ict_tabulado_via_the_committed_index(httpx_mock, monkeypatch, query):
    _mock_pages(httpx_mock, monkeypatch)
    censo_client._resources_cache.clear()
    result = await censo_client.search_censo_recursos(query)
    censo_client._resources_cache.clear()

    labels = [r["label"] for r in result["recursos"]]
    assert any("Tecnologías de la Información" in label for label in labels)
    ict = next(r for r in result["recursos"] if r["url"].endswith("03_2022_CPV_TIC.xlsx"))
    assert ict["tablas_coincidentes"], "the matching tables are returned"
    assert all("hoja" in t and "titulo" in t for t in ict["tablas_coincidentes"])
    assert "_hojas" not in ict
    assert "Población de 5+ años" in ict["contenido"]  # the hand-written description is kept


@pytest.mark.asyncio
async def test_search_matches_inside_tables_not_just_file_names(httpx_mock, monkeypatch):
    _mock_pages(httpx_mock, monkeypatch)
    censo_client._resources_cache.clear()
    # "tablet" is only a column header of the ICT workbook, not in any label.
    result = await censo_client.search_censo_recursos("tablet")
    censo_client._resources_cache.clear()
    assert result["recursos"] and all("TIC" in r["url"] for r in result["recursos"])
    assert "tablet" in json.dumps(result["recursos"][0]["tablas_coincidentes"], ensure_ascii=False).lower()


@pytest.mark.asyncio
async def test_network_failure_falls_back_to_the_committed_index(httpx_mock, monkeypatch):
    censo_client._resources_cache.clear()
    httpx_mock.add_exception(httpx.ConnectError("sin red"), is_reusable=True)
    result = await censo_client.search_censo_recursos("computadora")
    assert "aviso" in result and "índice incluido" in result["aviso"]
    assert result["recursos"] and result["recursos"][0]["tablas_coincidentes"]
    # The fallback is not cached: the next call tries the live site again.
    assert censo_client._resources_cache.get("resources") is None


@pytest.mark.asyncio
async def test_no_download_of_workbooks_at_query_time(httpx_mock, monkeypatch):
    _mock_pages(httpx_mock, monkeypatch)
    censo_client._resources_cache.clear()
    await censo_client.search_censo_recursos("internet")
    censo_client._resources_cache.clear()
    urls = [str(r.url) for r in httpx_mock.get_requests()]
    assert sorted(urls) == sorted([censo_client.RESULTADOS_URL, censo_client.DATA_URL])


@pytest.mark.asyncio
async def test_search_archivos_text_lists_the_matching_tables(httpx_mock, monkeypatch):
    from mcp.server.mcpserver import MCPServer

    from tools.search_archivos import register_search_archivos_tool

    _mock_pages(httpx_mock, monkeypatch)
    censo_client._resources_cache.clear()
    mcp = MCPServer("test")
    register_search_archivos_tool(mcp)
    fn = mcp._tool_manager.get_tool("search_archivos").fn

    text = (await fn(fuente="censo", query="computadora", limit=1)).content[0].text
    censo_client._resources_cache.clear()

    assert "· hoja 1:" in text and "[provincia]" in text
    assert "y " in text and "tabla(s) más" not in text or "más en este archivo" in text

import json

import pytest
from mcp.server.mcpserver import MCPServer

from helpers import ant_client
from tools.search_siniestros_ant import register_search_siniestros_ant_tool

_RESULT = {
    "query": "",
    "anio": None,
    "publicaciones_inec": [
        {
            "id": 2,
            "titulo": "Siniestros de Tránsito IV trimestre 2025",
            "fecha_publicacion": "2026-05-28",
            "url": "https://www.ecuadorencifras.gob.ec/p2/",
            "archivos": [
                {"format": "XLSX", "label": "Tabulados", "url": "https://x/tabulados.xlsx"}
            ],
        },
        {
            "id": 1,
            "titulo": "Siniestros de Tránsito III trimestre 2023",
            "fecha_publicacion": "2024-02-28",
            "url": "https://www.ecuadorencifras.gob.ec/p1/",
        },
    ],
    "datasets_ckan": [
        {
            "id": "fallecidos-sppat",
            "titulo": "Fallecidos SPPAT",
            "organizacion": "sppat",
            "modificado": "2022-05-12",
            "recursos": [{"nombre": "datos", "formato": "CSV", "url": "https://x/d.csv"}],
        }
    ],
    "avisos": ["Portal CKAN no respondió: HTTP 500"],
    "nota": "ant.gob.ec no responde.",
}


@pytest.fixture
def calls():
    return []


@pytest.fixture
def mcp(monkeypatch, calls):
    async def fake_search(**kwargs):
        calls.append(kwargs)
        return _RESULT

    monkeypatch.setattr(ant_client, "search_siniestros", fake_search)
    server = MCPServer("test")
    register_search_siniestros_ant_tool(server)
    return server


async def test_text_output_lists_inec_files_ckan_and_avisos(mcp, calls):
    result = await mcp.call_tool("search_siniestros_ant", {"anio": 2025, "limit": 5})

    text = result.content[0].text
    assert "- [2] Siniestros de Tránsito IV trimestre 2025 (2026-05-28)" in text
    assert "· XLSX: Tabulados — https://x/tabulados.xlsx" in text
    assert "- Fallecidos SPPAT (id: fallecidos-sppat, sppat)" in text
    assert "· CSV: datos — https://x/d.csv" in text
    assert "Aviso: Portal CKAN no respondió: HTTP 500" in text
    assert text.rstrip().endswith("ant.gob.ec no responde.")
    assert calls == [{"query": "", "anio": 2025, "limit": 5, "con_archivos": 2}]


async def test_json_output_returns_the_structured_result(mcp):
    result = await mcp.call_tool("search_siniestros_ant", {"format": "json"})

    assert json.loads(result.content[0].text) == _RESULT
    assert result.structured_content == _RESULT


async def test_text_output_reports_no_matches(monkeypatch, mcp):
    async def empty(**kwargs):
        return {**_RESULT, "publicaciones_inec": [], "datasets_ckan": [], "avisos": []}

    monkeypatch.setattr(ant_client, "search_siniestros", empty)

    text = (await mcp.call_tool("search_siniestros_ant", {})).content[0].text

    assert text.count("Sin coincidencias.") == 2

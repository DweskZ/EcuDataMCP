"""Dispatch and text rendering of the tools that merged several old ones
behind a `fuente`/`tipo` selector: list_catalogo, get_aviso_aeronautico,
get_serie_internacional, plus search_archivos' `formato` filter."""

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import tools.list_catalogo as list_catalogo_module
import tools.search_archivos as sa
from helpers import aviacion_client, irena_client, wdi_client, xm_client
from tools.aviso_aeronautico import register_aviso_aeronautico_tool
from tools.list_catalogo import register_list_catalogo_tool
from tools.serie_internacional import register_serie_internacional_tools


def _tool(register, name):
    mcp = MCPServer("test")
    register(mcp)
    return mcp._tool_manager.get_tool(name).fn


def _text(result):
    return result.content[0].text


# -- list_catalogo -----------------------------------------------------------


def test_every_catalog_has_a_text_builder():
    assert set(list_catalogo_module._SOURCES) == set(list_catalogo_module._TEXT)


async def test_list_catalogo_routes_to_the_source_and_tags_fuente(monkeypatch):
    async def fake_contraloria():
        return {"total": 1, "informes": [{"id": "7", "label": "2026 T1", "url": "https://c/7"}]}

    monkeypatch.setitem(list_catalogo_module._SOURCES, "contraloria", fake_contraloria)
    tool = _tool(register_list_catalogo_tool, "list_catalogo")

    result = await tool(fuente="contraloria")

    assert result.structured_content["fuente"] == "contraloria"
    assert "id=7: 2026 T1" in _text(result)


async def test_list_catalogo_wraps_source_errors(monkeypatch):
    async def broken():
        raise RuntimeError("portal caído")

    monkeypatch.setitem(list_catalogo_module._SOURCES, "arconel", broken)
    tool = _tool(register_list_catalogo_tool, "list_catalogo")

    with pytest.raises(ToolError, match="catálogo de arconel: portal caído"):
        await tool(fuente="arconel")


# -- get_aviso_aeronautico ---------------------------------------------------


async def test_aviso_requires_designador_except_for_sigmet(monkeypatch):
    async def fake_sigmet():
        return {"total": 0, "sigmets": [], "url_fuente": "https://ais"}

    monkeypatch.setattr(aviacion_client, "get_sigmet", fake_sigmet)
    tool = _tool(register_aviso_aeronautico_tool, "get_aviso_aeronautico")

    with pytest.raises(ToolError, match="obligatorio para metar"):
        await tool(tipo="metar")
    result = await tool(tipo="sigmet")
    assert "Sin SIGMET activos." in _text(result)
    assert result.structured_content["tipo"] == "sigmet"


async def test_aviso_metar_uppercases_designador(monkeypatch):
    seen = []

    async def fake_metar(icao):
        seen.append(icao)
        return {"designador": icao, "total": 0, "reportes": []}

    monkeypatch.setattr(aviacion_client, "get_metar", fake_metar)
    tool = _tool(register_aviso_aeronautico_tool, "get_aviso_aeronautico")

    await tool(tipo="metar", designador=" seqm ")

    assert seen == ["SEQM"]


# -- get_serie_internacional -------------------------------------------------


async def test_serie_wdi_without_indicador_searches_the_catalog(monkeypatch):
    async def fake_search(query, limit):
        return {"total": 1, "total_catalogo": 9, "indicadores": [{"indicador": "A.B", "nombre": query}]}

    monkeypatch.setattr(wdi_client, "search_indicadores", fake_search)
    tool = _tool(register_serie_internacional_tools, "get_serie_internacional")

    result = await tool(fuente="wdi", query="electricity")

    assert result.structured_content["fuente"] == "wdi"
    assert "- A.B: electricity" in _text(result)


async def test_serie_passes_years_to_wdi_and_irena(monkeypatch):
    calls = {}

    async def fake_wdi(indicador, pais, desde, hasta):
        calls["wdi"] = (desde, hasta)
        return {"indicador": indicador, "nombre": "X", "pais": pais, "total_registros": 0,
                "anios_sin_dato": 0, "serie": []}

    async def fake_irena(**kwargs):
        calls["irena"] = (kwargs["desde"], kwargs["hasta"])
        return {"pais": "Ecuador", "total_registros": 0, "registros": [], "tabla": "t"}

    monkeypatch.setattr(wdi_client, "get_indicador", fake_wdi)
    monkeypatch.setattr(irena_client, "get_electricidad", fake_irena)
    tool = _tool(register_serie_internacional_tools, "get_serie_internacional")

    await tool(fuente="wdi", indicador="A.B", desde="2015")
    await tool(fuente="irena", desde="2010", hasta="2020")

    assert calls == {"wdi": (2015, None), "irena": (2010, 2020)}


async def test_serie_xm_requires_both_dates_and_renders_zero_days(monkeypatch):
    async def fake_xm(desde, hasta, sentido, agregacion):
        return {"sentido": "Colombia → Ecuador", "desde": desde, "hasta": hasta, "total_gwh": 0.0,
                "total_por_periodo": {desde: 0.0}, "registros": []}

    monkeypatch.setattr(xm_client, "get_intercambio", fake_xm)
    tool = _tool(register_serie_internacional_tools, "get_serie_internacional")

    with pytest.raises(ToolError, match="xm requiere"):
        await tool(fuente="xm", desde="2024-10-01")
    result = await tool(fuente="xm", desde="2024-10-01", hasta="2024-10-01")
    assert "- 2024-10-01: 0.0 GWh" in _text(result)


async def test_serie_rejects_non_year_for_wdi():
    tool = _tool(register_serie_internacional_tools, "get_serie_internacional")

    with pytest.raises(ToolError, match="debe ser un año"):
        await tool(fuente="wdi", indicador="A.B", desde="ayer")


# -- search_archivos formato -------------------------------------------------


async def test_search_archivos_formato_filters_before_paginating(monkeypatch):
    async def fake(query=""):
        files = [{"titulo": f"p{i}", "url": f"https://b/{i}", "formato": fmt}
                 for i, fmt in enumerate(["PDF", "XLSX", "PDF", "XLSX", "XLSX"])]
        return {"publicaciones": files}

    monkeypatch.setitem(sa._UNPAGINATED, "bce_publicaciones", fake)

    result = await sa._search("bce_publicaciones", "", limit=2, offset=0, formato="xlsx")

    assert result["total"] == 3
    assert [a["titulo"] for a in result["archivos"]] == ["p1", "p3"]


async def test_search_archivos_formato_rejected_for_paginated_sources():
    with pytest.raises(ValueError, match="no está disponible para censo"):
        await sa._search("censo", "", limit=5, offset=0, formato="CSV")

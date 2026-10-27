import re

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from helpers import arcgis_client as client
from tools.geoportal import register_geoportal_tools

_BALANCE = client._entry("arconel", "balance_energia")["url"]
_META = {
    "type": "Table",
    "geometryType": None,
    "objectIdField": "IdResumenBalanceEnergia",
    "fields": [
        {"name": "IdResumenBalanceEnergia", "type": "esriFieldTypeOID"},
        {"name": "Empresa", "type": "esriFieldTypeString"},
        {"name": "Anio", "type": "esriFieldTypeInteger"},
        {"name": "FechaHoraDemandaMaxima", "type": "esriFieldTypeDate"},
    ],
}
_ROW = {
    "IdResumenBalanceEnergia": 22718,
    # As the cloud layer serves it: UTF-8 bytes read as latin-1.
    "Empresa": "CNEL-BolÃ\xadvar",
    "Anio": 2024,
    "FechaHoraDemandaMaxima": 1713225600000,
}


def _query(kind: str) -> re.Pattern:
    """Match the layer's count or rows query, whatever the parameter order."""
    marker = "returnCountOnly=true" if kind == "count" else "resultRecordCount="
    return re.compile(rf"^{re.escape(_BALANCE)}/query\?.*{marker}")


@pytest.fixture(autouse=True)
def clear_cache():
    client._meta_cache.clear()
    yield
    client._meta_cache.clear()


async def test_search_capas_filters_by_text():
    result = await client.search_capas("arconel", "perdidas")

    assert [c["capa"] for c in result["capas"]] == ["balance_energia"]
    assert result["total_en_catalogo"] == 6


async def test_celec_catalog_excludes_survey_layers():
    urls = [e["url"] for e in client._CATALOGO["celec"]]

    assert not any("survey123" in u.lower() or "encuesta" in u.lower() for u in urls)


async def test_get_layer_features_repairs_text_and_dates(httpx_mock):
    httpx_mock.add_response(url=f"{_BALANCE}?f=json", json=_META)
    httpx_mock.add_response(url=_query("count"), json={"count": 20})
    httpx_mock.add_response(
        url=_query("rows"),
        json={"features": [{"attributes": _ROW}], "exceededTransferLimit": True},
    )

    result = await client.get_layer_features(
        "arconel", "balance_energia", count=1, filtro="Anio = 2024"
    )

    props = result["features"][0]["propiedades"]
    assert props["Empresa"] == "CNEL-Bolívar"
    assert props["FechaHoraDemandaMaxima"] == "2024-04-16"
    assert result["features"][0]["id"] == 22718
    assert result["total_features_en_capa"] == 20
    assert result["hay_mas"] is True
    assert result["filtro"] == "Anio = 2024"
    assert "resultOffset=0" in result["url_consulta"]


async def test_get_layer_features_caps_count(httpx_mock):
    httpx_mock.add_response(url=f"{_BALANCE}?f=json", json=_META)
    httpx_mock.add_response(url=_query("count"), json={"count": 6078})
    httpx_mock.add_response(url=_query("rows"), json={"features": []})

    result = await client.get_layer_features("arconel", "balance_energia", count=9999)

    assert f"resultRecordCount={client.MAX_FEATURE_COUNT}" in result["url_consulta"]
    assert "where=1%3D1" in result["url_consulta"]


async def test_arcgis_error_payload_raises(httpx_mock):
    httpx_mock.add_response(url=f"{_BALANCE}?f=json", json=_META)
    httpx_mock.add_response(
        url=_query("count"),
        json={"error": {"code": 400, "message": "", "details": ["'where' parameter is invalid"]}},
    )

    with pytest.raises(ValueError, match="where' parameter is invalid"):
        await client.get_layer_features("arconel", "balance_energia", filtro="nope ==")


async def test_unknown_capa_lists_valid_ones():
    with pytest.raises(ValueError, match="balance_energia"):
        await client.get_layer_features("arconel", "no_existe")


async def test_tools_route_arcgis_and_reject_filters_on_geoserver(httpx_mock):
    httpx_mock.add_response(url=f"{_BALANCE}?f=json", json=_META)
    httpx_mock.add_response(url=_query("count"), json={"count": 3})
    httpx_mock.add_response(url=_query("rows"), json={"features": [{"attributes": _ROW}]})
    server = MCPServer("test")
    register_geoportal_tools(server)

    listed = await server.call_tool("search_capas_geo", {"fuente": "celec"})
    assert "[ArcGIS REST]" in listed.content[0].text

    got = await server.call_tool(
        "get_capa_geo_datos",
        {"fuente": "arconel", "capa": "balance_energia", "count": 1, "filtro": "Anio = 2024"},
    )
    text = got.content[0].text
    assert "Filtro: Anio = 2024" in text
    assert "Hay más filas: repite con offset=1." in text

    with pytest.raises(ToolError, match="solo aplican"):
        await server.call_tool(
            "get_capa_geo_datos", {"fuente": "inamhi", "capa": "x", "filtro": "a = 1"}
        )

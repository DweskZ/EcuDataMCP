import asyncio
import json
import re
import socket
import time
from datetime import date

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from helpers import nasa_power_client
from tools import register_tools
from tools.get_clima_nasa_power import register_get_clima_nasa_power_tool


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_DISK_CACHE", "0")

    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    nasa_power_client._cache.clear()
    yield
    nasa_power_client._cache.clear()


_DAILY_URL = re.compile(r"https://power\.larc\.nasa\.gov/api/temporal/daily/point\?.*")
_MONTHLY_URL = re.compile(r"https://power\.larc\.nasa\.gov/api/temporal/monthly/point\?.*")


def _daily_payload():
    # Shaped like the live response for Quito: the last two days are not
    # published yet and come back as the fill value -999 with HTTP 200.
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-78.519, -0.104, 1862.95]},
        "properties": {
            "parameter": {
                "PRECTOTCORR": {
                    "20240101": 0.74,
                    "20240102": -999.0,
                    "20240103": 8.62,
                    "20240104": -999.0,
                    "20240105": -999.0,
                },
                "T2M": {
                    "20240101": 18.13,
                    "20240102": 18.27,
                    "20240103": 17.59,
                    "20240104": -999.0,
                    "20240105": -999.0,
                },
            }
        },
        "header": {"sources": ["GEOSIT"], "fill_value": -999.0},
    }


def _monthly_payload():
    months = {"202312": 6.1, "202313": 3.93, "202401": 3.47, "202402": 5.6, "202403": 4.61}
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-78.519, -0.104, 1862.95]},
        "properties": {
            "parameter": {
                "PRECTOTCORR": months,
                "T2M": {k: 18.0 for k in months},
            }
        },
        "header": {"sources": ["MERRA2"]},
    }


def test_dates_expand_to_the_start_or_the_end_of_the_period():
    assert nasa_power_client.parse_date("2024", end=False) == date(2024, 1, 1)
    assert nasa_power_client.parse_date("2024", end=True) == date(2024, 12, 31)
    assert nasa_power_client.parse_date("2024-02", end=True) == date(2024, 2, 29)
    assert nasa_power_client.parse_date("20240315", end=False) == date(2024, 3, 15)
    with pytest.raises(ValueError, match="no válida"):
        nasa_power_client.parse_date("2024-13", end=False)


async def test_daily_fill_values_become_none_and_trailing_days_are_dropped(httpx_mock):
    httpx_mock.add_response(url=_DAILY_URL, json=_daily_payload())

    result = await nasa_power_client.get_clima(
        -0.104, -78.5192, desde="2024-01-01", hasta="2024-01-05", frecuencia="diaria"
    )

    request = httpx_mock.get_requests()[0]
    assert request.url.params["parameters"] == "PRECTOTCORR,T2M"
    assert request.url.params["start"] == "20240101"
    assert request.url.params["end"] == "20240105"
    assert request.url.params["community"] == "AG"
    assert [r["periodo"] for r in result["registros"]] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
    ]
    assert result["registros"][1] == {"periodo": "2024-01-02", "lluvia": None, "temperatura": 18.27}
    assert result["ultimo_periodo_con_dato"] == "2024-01-03"
    assert result["metadatos"]["fecha_corte"] == "2024-01-03"
    assert result["resumen"]["lluvia"]["acumulado_mm"] == 9.4
    assert result["resumen"]["lluvia"]["periodos_con_dato"] == 2
    assert result["punto"]["elevacion_m"] == 1862.95
    assert result["fuentes_datos"] == ["GEOSIT"]


async def test_monthly_drops_the_annual_mean_and_months_outside_the_period(httpx_mock):
    httpx_mock.add_response(url=_MONTHLY_URL, json=_monthly_payload())

    result = await nasa_power_client.get_clima(
        -0.104, -78.5192, desde="2024-01", hasta="2024-02", frecuencia="mensual"
    )

    request = httpx_mock.get_requests()[0]
    assert request.url.params["start"] == "2024"
    assert request.url.params["end"] == "2024"
    assert [r["periodo"] for r in result["registros"]] == ["2024-01", "2024-02"]
    # mm/day times the days of each month: 3.47 x 31 + 5.6 x 29 (2024 is a leap year).
    assert result["resumen"]["lluvia"]["acumulado_mm"] == 270.0
    assert result["resumen"]["temperatura"]["media"] == 18.0


async def test_a_422_from_the_api_surfaces_its_reason(httpx_mock):
    httpx_mock.add_response(
        url=_DAILY_URL,
        status_code=422,
        json={"header": "failed", "messages": ["One of your parameters is incorrect: NOPE."]},
    )

    with pytest.raises(ValueError, match="parameters is incorrect: NOPE"):
        await nasa_power_client.get_clima(
            -0.104, -78.5192, desde="2024-01-01", hasta="2024-01-05", frecuencia="diaria"
        )


async def test_the_last_good_answer_is_served_when_the_host_goes_down(httpx_mock):
    httpx_mock.add_response(url=_MONTHLY_URL, json=_monthly_payload())
    first = await nasa_power_client.get_clima(-0.104, -78.5192, desde="2024-01", hasta="2024-03")

    # Expire the cached copy, then make the host refuse the next fetch.
    for key, (_, value) in list(nasa_power_client._cache._store.items()):
        nasa_power_client._cache._store[key] = (time.time() - 1, value)
    httpx_mock.add_exception(httpx.ConnectError("down"), url=_MONTHLY_URL)

    again = await nasa_power_client.get_clima(-0.104, -78.5192, desde="2024-01", hasta="2024-03")

    assert again["registros"] == first["registros"]


async def test_period_limits_are_explained_before_calling_the_api():
    with pytest.raises(ValueError, match="1981"):
        await nasa_power_client.get_clima(-0.104, -78.5192, desde="1975")
    with pytest.raises(ValueError, match="máximo 366 días"):
        await nasa_power_client.get_clima(
            -0.104, -78.5192, desde="2023-01-01", hasta="2024-12-31", frecuencia="diaria"
        )
    with pytest.raises(ValueError, match="posterior"):
        await nasa_power_client.get_clima(-0.104, -78.5192, desde="2024-05", hasta="2024-01")
    with pytest.raises(ValueError, match="Disponibles"):
        await nasa_power_client.get_clima(-0.104, -78.5192, variables="lluvia,nieve")


async def test_default_daily_period_is_the_last_thirty_days(monkeypatch):
    monkeypatch.setattr(nasa_power_client, "today_ecuador", lambda: date(2026, 11, 24))

    start, stop = nasa_power_client.resolve_period("", "", "diaria")

    assert (start, stop) == (date(2026, 10, 26), date(2026, 11, 24))
    assert nasa_power_client.resolve_period("", "2030-01-01", "diaria")[1] == date(2026, 11, 24)


def _server():
    server = MCPServer("test")
    register_get_clima_nasa_power_tool(server)
    return server


async def test_tool_queries_the_canton_centroid(httpx_mock):
    httpx_mock.add_response(url=_MONTHLY_URL, json=_monthly_payload())

    result = await _server().call_tool(
        "get_clima_nasa_power",
        {"canton": "Quito", "desde": "2024-01", "hasta": "2024-03", "format": "json"},
    )
    payload = json.loads(result.content[0].text)

    request = httpx_mock.get_requests()[0]
    assert request.url.params["latitude"] == "-0.104"
    assert request.url.params["longitude"] == "-78.5192"
    assert payload["canton"] == {"codigo": "1701", "nombre": "Quito", "provincia": "Pichincha"}
    assert payload["metadatos"]["contrato"] == "ecudatamcp.response.v1"


async def test_tool_text_names_the_canton_units_and_summary(httpx_mock):
    httpx_mock.add_response(url=_MONTHLY_URL, json=_monthly_payload())

    text = (
        await _server().call_tool(
            "get_clima_nasa_power", {"canton": "1701", "desde": "2024-01", "hasta": "2024-03"}
        )
    ).content[0].text

    assert "Quito (Pichincha)" in text
    assert "- 2024-01: lluvia 3.47 mm/día, temperatura 18.0 °C" in text
    assert "acumulado" in text


async def test_tool_accepts_plain_coordinates(httpx_mock):
    httpx_mock.add_response(url=_MONTHLY_URL, json=_monthly_payload())

    result = await _server().call_tool(
        "get_clima_nasa_power",
        {"latitud": -2.17, "longitud": -79.9, "desde": "2024-01", "hasta": "2024-03", "format": "json"},
    )
    payload = json.loads(result.content[0].text)

    assert "canton" not in payload
    assert httpx_mock.get_requests()[0].url.params["latitude"] == "-2.17"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ({}, "Indica un `canton`"),
        ({"canton": "Quito", "latitud": -0.1, "longitud": -78.5}, "no ambos"),
        ({"latitud": -0.1}, "juntas"),
        ({"canton": "Bolivar"}, "coincide con 2 cantones"),
        ({"canton": "Sevilla Don Bosco"}, "no tiene centroide"),
        ({"canton": "Atlantida"}, "No encontré el cantón"),
    ],
)
async def test_tool_explains_what_to_fix(args, message):
    with pytest.raises(Exception, match=message):
        await _server().call_tool("get_clima_nasa_power", args)


async def test_an_ambiguous_name_is_settled_by_the_province(httpx_mock):
    httpx_mock.add_response(url=_MONTHLY_URL, json=_monthly_payload())

    result = await _server().call_tool(
        "get_clima_nasa_power",
        {"canton": "Bolivar", "provincia": "Carchi", "desde": "2024-01", "hasta": "2024-03", "format": "json"},
    )

    assert json.loads(result.content[0].text)["canton"]["codigo"] == "0402"


def _registered(monkeypatch, **env) -> set[str]:
    for name in ("ECUADOR_MCP_HIDE_TOOLS", "ECUADOR_MCP_HIDE_GEOBLOCKED", "ECUADOR_MCP_GEO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    server = MCPServer("test")
    register_tools(server)
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_the_tool_is_registered_and_can_be_hidden_by_name(monkeypatch):
    assert "get_clima_nasa_power" in _registered(monkeypatch)
    assert "get_clima_nasa_power" not in _registered(
        monkeypatch, ECUADOR_MCP_HIDE_TOOLS="get_clima_nasa_power"
    )

import re

import pytest

from helpers import (
    comtrade_client,
    ilo_client,
    imf_client,
    intl_http,
    sdmx_json,
    unhcr_client,
    who_client,
)
from tools import serie_internacional as tool


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(intl_http, "_sleep", fake_sleep)
    caches = (
        comtrade_client._data_cache,
        imf_client._flows_cache,
        imf_client._data_cache,
        ilo_client._flows_cache,
        ilo_client._data_cache,
        who_client._catalog_cache,
        who_client._data_cache,
        unhcr_client._data_cache,
    )
    for c in caches:
        c.clear()
    yield waits
    for c in caches:
        c.clear()


# ---------------------------------------------------------------- Comtrade

_COMTRADE_URL = re.compile(r"https://comtradeapi\.un\.org/public/v1/preview/C/A/HS\?.*")


def _row(flow: str, value: float, cmd: str = "TOTAL", partner: int = 842) -> dict:
    return {
        "period": "2023",
        "flowCode": flow,
        "partnerCode": partner,
        "cmdCode": cmd,
        "primaryValue": value,
        "netWgt": 0.0,
        "qty": 0.0,
    }


async def test_comtrade_parses_and_sends_codes(httpx_mock):
    httpx_mock.add_response(
        url=_COMTRADE_URL, json={"count": 2, "data": [_row("X", 7.4e9), _row("M", 8.3e9)]}
    )

    result = await comtrade_client.get_comercio(periodo="2023", socio="USA")

    request = httpx_mock.get_requests()[0]
    assert request.url.params["reporterCode"] == "218"
    assert request.url.params["partnerCode"] == "842"
    assert request.url.params["flowCode"] == "X,M"
    assert [r["flujo"] for r in result["registros"]] == ["exportaciones", "importaciones"]
    assert result["truncado_500"] is False


async def test_comtrade_retries_429_honouring_message(httpx_mock, isolate):
    httpx_mock.add_response(
        url=_COMTRADE_URL,
        status_code=429,
        text='{ "statusCode": 429, "message": "Rate limit is exceeded. Try again in 2 seconds." }',
    )
    httpx_mock.add_response(url=_COMTRADE_URL, json={"count": 1, "data": [_row("X", 1.0)]})

    result = await comtrade_client.get_comercio(periodo="2023", flujo="X")

    assert result["total_registros"] == 1
    assert isolate == [3.0]  # 2 s from the message plus a 1 s margin


async def test_comtrade_gives_up_after_three_429(httpx_mock):
    for _ in range(3):
        httpx_mock.add_response(url=_COMTRADE_URL, status_code=429, text="Try again in 2 seconds")

    with pytest.raises(ValueError, match="límite de tasa"):
        await comtrade_client.get_comercio(periodo="2023")


async def test_comtrade_flags_500_row_cap(httpx_mock):
    rows = [_row("X", float(i), cmd=str(i)) for i in range(500)]
    httpx_mock.add_response(url=_COMTRADE_URL, json={"count": 500, "data": rows})

    result = await comtrade_client.get_comercio(periodo="2023", cmd="27", socio="0")

    assert result["truncado_500"] is True


async def test_comtrade_validates_before_calling():
    with pytest.raises(ValueError, match="un solo período"):
        await comtrade_client.get_comercio(periodo="2022,2023")
    with pytest.raises(ValueError, match="AAAAMM"):
        await comtrade_client.get_comercio(periodo="2023", frecuencia="M")
    with pytest.raises(ValueError, match="M49"):
        await comtrade_client.get_comercio(periodo="2023", socio="Atlantis")


# --------------------------------------------------------------------- IMF

_IMF_DATA = {
    "header": {"id": "x"},
    "dataSets": [
        {
            "series": {
                "0:0:0:0:0": {"observations": {"0": ["100.5", None], "1": ["101", None]}}
            }
        }
    ],
    "structure": {
        "name": "Consumer Price Index (CPI)",
        "dimensions": {
            "series": [
                {"id": "COUNTRY", "keyPosition": 0, "values": [{"id": "ECU", "name": "Ecuador"}]},
                {"id": "INDEX_TYPE", "keyPosition": 1, "values": [{"id": "CPI", "name": "CPI"}]},
                {"id": "FREQUENCY", "keyPosition": 2, "values": [{"id": "M", "name": "Monthly"}]},
                {"id": "UNIT", "keyPosition": 3, "values": [{"id": "IX", "name": "Index"}]},
                {"id": "COICOP", "keyPosition": 4, "values": [{"id": "_T", "name": "All Items"}]},
            ],
            "observation": [
                {
                    "id": "TIME_PERIOD",
                    "values": [{"id": "2026-M06"}, {"id": "2026-M07"}],
                }
            ],
        },
    },
}


async def test_imf_defaults_to_country_prefix_and_last_observations(httpx_mock):
    httpx_mock.add_response(
        url="https://api.imf.org/external/sdmx/2.1/data/IMF.STA,CPI/ECU?lastNObservations=5",
        json=_IMF_DATA,
    )

    result = await imf_client.get_serie("CPI")

    assert result["clave_consulta"] == "ECU"
    assert [d["id"] for d in result["dimensiones"]] == [
        "COUNTRY",
        "INDEX_TYPE",
        "FREQUENCY",
        "UNIT",
        "COICOP",
    ]
    serie = result["series"][0]
    assert serie["clave"] == "ECU.CPI.M.IX._T"
    assert serie["observaciones"] == [
        {"periodo": "2026-M06", "valor": 100.5},
        {"periodo": "2026-M07", "valor": 101},
    ]


async def test_imf_period_range_replaces_last_n(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r".*/data/IMF\.STA,CPI/ECU\.CPI\?startPeriod=2024&endPeriod=2025$"),
        json=_IMF_DATA,
    )

    await imf_client.get_serie("CPI", clave="ECU.CPI", desde="2024", hasta="2025")


async def test_imf_no_content_is_a_clear_error(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*/data/IMF\.STA,CPI/.*"), status_code=204)

    with pytest.raises(ValueError, match="no devolvió datos"):
        await imf_client.get_serie("CPI", clave="XXX")


async def test_imf_flow_search_is_cached(httpx_mock):
    httpx_mock.add_response(
        url="https://api.imf.org/external/sdmx/2.1/dataflow/IMF.STA",
        json={
            "data": {
                "dataflows": [
                    {"id": "CPI", "name": "Consumer Price Index (CPI)"},
                    {"id": "BOP", "name": "Balance of Payments"},
                ]
            }
        },
    )

    first = await imf_client.search_flujos("price")
    second = await imf_client.search_flujos("balance")  # served from the cache

    assert [f["flujo"] for f in first["flujos"]] == ["CPI"]
    assert [f["flujo"] for f in second["flujos"]] == ["BOP"]


async def test_imf_rejects_bad_key_and_period():
    with pytest.raises(ValueError, match="Clave"):
        await imf_client.get_serie("CPI", clave="ECU/../x")
    with pytest.raises(ValueError, match="desde"):
        await imf_client.get_serie("CPI", desde="enero")


def test_sdmx_json_series_cap():
    payload = {
        "dataSets": [{"series": {f"{i}": {"observations": {"0": [i]}} for i in range(5)}}],
        "structure": {
            "dimensions": {
                "series": [
                    {
                        "id": "D",
                        "keyPosition": 0,
                        "values": [{"id": str(i), "name": str(i)} for i in range(5)],
                    }
                ],
                "observation": [{"values": [{"id": "2024"}]}],
            }
        },
    }

    parsed = sdmx_json.parse(payload, max_series=2)

    assert parsed["total_series"] == 5
    assert len(parsed["series"]) == 2


# --------------------------------------------------------------------- ILO

_ILO_DATA = {
    "data": {
        "structures": [
            {
                "dimensions": {
                    "series": [
                        {
                            "id": "REF_AREA",
                            "keyPosition": 0,
                            "values": [{"id": "ECU", "name": "Ecuador"}],
                        },
                        {"id": "FREQ", "keyPosition": 1, "values": [{"id": "A", "name": "Annual"}]},
                    ],
                    "observation": [{"values": [{"id": "2024"}, {"id": "2025"}]}],
                }
            }
        ],
        "dataSets": [{"series": {"0:0": {"observations": {"1": [3.232, 0, 0]}}}}],
    }
}


async def test_ilo_pads_short_key_after_422(httpx_mock):
    base = "https://sdmx.ilo.org/rest/data/ILO,DF_UNE_DEAP_SEX_AGE_RT"
    httpx_mock.add_response(
        url=re.compile(re.escape(base) + r"/ECU\.A\?.*"),
        status_code=422,
        text="Not enough key values in query, expecting 5 got 2",
    )
    httpx_mock.add_response(url=re.compile(re.escape(base) + r"/ECU\.A\.\.\.\?.*"), json=_ILO_DATA)

    result = await ilo_client.get_serie("UNE_DEAP_SEX_AGE_RT", clave="ECU.A", ultimos=1)

    assert result["flujo"] == "DF_UNE_DEAP_SEX_AGE_RT"
    assert result["clave_consulta"] == "ECU.A..."
    assert result["series"][0]["observaciones"] == [{"periodo": "2025", "valor": 3.232}]
    assert httpx_mock.get_requests()[0].url.params["format"] == "jsondata"


async def test_ilo_404_means_unknown_flow_or_key(httpx_mock):
    httpx_mock.add_response(url=re.compile(r"https://sdmx\.ilo\.org/rest/data/.*"), status_code=404)

    with pytest.raises(ValueError, match="flujo o clave inexistente"):
        await ilo_client.get_serie("DF_NOPE")


async def test_ilo_flow_search(httpx_mock):
    httpx_mock.add_response(
        url="https://sdmx.ilo.org/rest/dataflow/ILO?detail=allstubs",
        json={
            "data": {
                "dataflows": [
                    {"id": "DF_UNE_DEAP_SEX_AGE_RT", "name": "Unemployment rate by sex and age"},
                    {"id": "DF_EMP_TEMP_SEX_AGE_NB", "name": "Employment by sex and age"},
                ]
            }
        },
    )

    result = await ilo_client.search_flujos("UNEMPLOYMENT")

    assert [f["flujo"] for f in result["flujos"]] == ["DF_UNE_DEAP_SEX_AGE_RT"]


# --------------------------------------------------------------------- WHO


async def test_who_search_matches_name(httpx_mock):
    httpx_mock.add_response(
        url="https://ghoapi.azureedge.net/api/Indicator",
        json={
            "value": [
                {"IndicatorCode": "WHOSIS_000001", "IndicatorName": "Life expectancy at birth (years)"},
                {"IndicatorCode": "MDG_0000000001", "IndicatorName": "Infant mortality rate"},
            ]
        },
    )

    result = await who_client.search_indicadores("life")

    assert [i["indicador"] for i in result["indicadores"]] == ["WHOSIS_000001"]
    assert result["total_catalogo"] == 2


async def test_who_series_filters_country_and_years(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r"https://ghoapi\.azureedge\.net/api/WHOSIS_000001\?.*"),
        json={
            "value": [
                {"TimeDim": 2022, "Dim1": "SEX_BTSX", "NumericValue": 77.3, "Low": 76.0, "High": 78.0},
                {"TimeDim": 2017, "Dim1": "SEX_BTSX", "NumericValue": 78.6, "Value": "78.6 [78-79.1]"},
            ]
        },
    )

    result = await who_client.get_indicador("WHOSIS_000001", desde=2015, hasta=2023)

    flt = httpx_mock.get_requests()[0].url.params["$filter"]
    assert flt == "SpatialDim eq 'ECU' and TimeDim ge 2015 and TimeDim le 2023"
    assert [r["anio"] for r in result["serie"]] == [2017, 2022]
    assert result["serie"][1]["bajo"] == 76.0


async def test_who_empty_result_is_a_clear_error(httpx_mock):
    httpx_mock.add_response(url=re.compile(r"https://ghoapi\.azureedge\.net/api/NOPE.*"), json={"value": []})

    with pytest.raises(ValueError, match="no tiene datos"):
        await who_client.get_indicador("NOPE_1")


async def test_who_rejects_injection_in_codes():
    with pytest.raises(ValueError, match="indicador"):
        await who_client.get_indicador("A' or 1 eq 1")
    with pytest.raises(ValueError, match="país"):
        await who_client.get_indicador("WHOSIS_000001", pais="EC'U")


# ------------------------------------------------------------------- UNHCR

_UNHCR_URL = re.compile(r"https://api\.unhcr\.org/population/v1/population/\?.*")


def _unhcr_item(year: int, coo: str, refugees, asylum="0", oip="-") -> dict:
    return {
        "year": year,
        "coo": coo,
        "coo_name": coo,
        "refugees": refugees,
        "asylum_seekers": asylum,
        "returned_refugees": "0",
        "idps": "0",
        "returned_idps": "0",
        "stateless": "0",
        "ooc": "0",
        "oip": oip,
        "hst": "0",
    }


async def test_unhcr_follows_pages_and_normalises_numbers(httpx_mock):
    httpx_mock.add_response(
        url=_UNHCR_URL,
        json={"page": 1, "maxPages": 2, "items": [_unhcr_item(2024, "VEN", 2493, 3188, 439097)]},
    )
    httpx_mock.add_response(
        url=_UNHCR_URL,
        json={"page": 2, "maxPages": 2, "items": [_unhcr_item(2024, "COL", 19710, "3626")]},
    )

    result = await unhcr_client.get_poblacion(desde=2024, hasta=2024, origen="todos")

    first = httpx_mock.get_requests()[0].url.params
    assert first["coa"] == "ECU"
    assert first["coo_all"] == "true"
    assert first["yearFrom"] == "2024"
    assert [r["origen"] for r in result["registros"]] == ["COL", "VEN"]
    col = result["registros"][0]
    assert col["solicitantes_asilo"] == 3626  # "3626" string becomes int
    assert col["otras_personas_necesitan_proteccion_internacional"] is None  # "-"
    assert result["paginas_leidas"] == 2


async def test_unhcr_totals_row_has_no_origin(httpx_mock):
    httpx_mock.add_response(
        url=_UNHCR_URL,
        json={"page": 1, "maxPages": 1, "items": [_unhcr_item(2023, "-", 62899)]},
    )

    result = await unhcr_client.get_poblacion()

    assert result["registros"][0]["origen"] == "Total"


async def test_unhcr_validates_origin():
    with pytest.raises(ValueError, match="ISO3"):
        await unhcr_client.get_poblacion(origen="Venezuela")


# -------------------------------------------------------------------- tool


async def test_tool_dispatch_and_text_for_new_sources(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r"https://api\.unhcr\.org/.*"),
        json={"page": 1, "maxPages": 1, "items": [_unhcr_item(2024, "VEN", 2493)]},
    )
    params = {
        "indicador": "",
        "query": "",
        "pais": "ECU",
        "desde": "2024",
        "hasta": "2024",
        "limit": 30,
        "periodo": "",
        "socio": "VEN",
        "cmd": "TOTAL",
        "flujo": "ambos",
        "frecuencia": "A",
        "clave": "",
        "ultimos": 0,
    }

    data = await tool._run("unhcr", params)
    text = tool._to_text(data)

    assert data["fuente"] == "unhcr"
    assert "2024 | VEN: refugiados 2493" in text


async def test_http_error_message_names_source(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*ghoapi.*"), status_code=400, text="Bad things")

    with pytest.raises(ValueError, match=r"OMS respondió HTTP 400"):
        await who_client.search_indicadores("x")


# ------------------------------------------------------- hardening follow-ups


async def test_5xx_retry_ignores_seconds_text_in_body(httpx_mock, isolate):
    httpx_mock.add_response(url=re.compile(r".*ghoapi.*"), status_code=503, text="back in 9 seconds")
    httpx_mock.add_response(url=re.compile(r".*ghoapi.*"), json={"value": []})

    await who_client.search_indicadores("x")

    assert isolate == [2.0]  # backoff, not the 9 s quoted by the 5xx body


async def test_connect_error_is_retried_then_named(httpx_mock, isolate):
    import httpx

    for _ in range(3):
        httpx_mock.add_exception(httpx.ConnectError("boom"), url=re.compile(r".*ghoapi.*"))

    with pytest.raises(ValueError, match=r"OMS no se pudo conectar \(ConnectError\)"):
        await who_client.search_indicadores("x")

    assert len(isolate) == 2


async def test_imf_unknown_flow_and_bad_key_are_clear_errors(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*/data/IMF\.STA,NOPE/.*"), status_code=404, text="No such dataflow")
    httpx_mock.add_response(url=re.compile(r".*/data/IMF\.STA,CPI/XXX.*"), status_code=400, text="Jackson error")

    with pytest.raises(ValueError, match="no tiene el flujo 'NOPE'"):
        await imf_client.get_serie("NOPE")
    with pytest.raises(ValueError, match="rechazó la clave 'XXX'"):
        await imf_client.get_serie("CPI", clave="XXX")


def test_sdmx_json_out_of_range_position_is_a_clear_error():
    payload = {
        "dataSets": [{"series": {"3": {"observations": {"0": [1]}}}}],
        "structure": {
            "dimensions": {
                "series": [{"id": "D", "keyPosition": 0, "values": [{"id": "a", "name": "a"}]}],
                "observation": [{"values": [{"id": "2024"}]}],
            }
        },
    }

    with pytest.raises(ValueError, match="inconsistente"):
        sdmx_json.parse(payload)


async def test_unhcr_flags_truncation_at_page_cap(httpx_mock):
    for page in range(1, 11):
        httpx_mock.add_response(
            url=_UNHCR_URL,
            json={"page": page, "maxPages": 12, "items": [_unhcr_item(2000 + page, "VEN", 1)]},
        )

    result = await unhcr_client.get_poblacion(origen="todos")

    assert result["truncado"] is True
    assert result["paginas_leidas"] == 10
    assert "truncado" in tool._to_text({"fuente": "unhcr", **result})


def test_retry_after_http_date_is_honoured_and_clamped():
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    import httpx

    soon = format_datetime(datetime.now(UTC) + timedelta(seconds=6), usegmt=True)
    far = format_datetime(datetime.now(UTC) + timedelta(hours=1), usegmt=True)
    past = format_datetime(datetime.now(UTC) - timedelta(seconds=30), usegmt=True)

    wait_soon = intl_http._wait_seconds(httpx.Response(429, headers={"Retry-After": soon}), 1)
    wait_far = intl_http._wait_seconds(httpx.Response(429, headers={"Retry-After": far}), 1)
    wait_past = intl_http._wait_seconds(httpx.Response(429, headers={"Retry-After": past}), 1)
    wait_junk = intl_http._wait_seconds(httpx.Response(429, headers={"Retry-After": "soon"}), 1)

    assert 4.0 < wait_soon <= 6.0
    assert wait_far == intl_http._MAX_WAIT_SECONDS
    assert wait_past == 2.0  # backoff, not a negative or zero wait
    assert wait_junk == 2.0


def test_sdmx_json_observation_outside_period_list_is_a_clear_error():
    payload = {
        "dataSets": [{"series": {"0": {"observations": {"0": [1], "5": [2]}}}}],
        "structure": {
            "dimensions": {
                "series": [{"id": "D", "keyPosition": 0, "values": [{"id": "a", "name": "a"}]}],
                "observation": [{"values": [{"id": "2024"}]}],
            }
        },
    }

    with pytest.raises(ValueError, match="período inexistente"):
        sdmx_json.parse(payload)

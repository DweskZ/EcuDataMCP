import pytest

from helpers import wdi_client as client

_CATALOG = [
    {"page": 1, "pages": 1, "per_page": "5000", "total": 2},
    [
        {
            "id": "EG.ELC.ACCS.ZS",
            "name": "Access to electricity (% of population)",
            "sourceNote": "Access to electricity is the percentage of population.",
            "sourceOrganization": "World Bank",
        },
        {
            "id": "NY.GDP.MKTP.CD",
            "name": "GDP (current US$)",
            "sourceNote": "",
            "sourceOrganization": "",
        },
    ],
]

_NAME = "Access to electricity (% of population)"
_SERIES = [
    {"page": 1, "pages": 1, "per_page": 1000, "total": 3, "lastupdated": "2026-07-13"},
    [
        {
            "indicator": {"id": "EG.ELC.ACCS.ZS", "value": _NAME},
            "country": {"id": "EC", "value": "Ecuador"},
            "date": "2024",
            "value": 98.5,
        },
        {
            "indicator": {"id": "EG.ELC.ACCS.ZS", "value": _NAME},
            "country": {"id": "EC", "value": "Ecuador"},
            "date": "2023",
            "value": None,
        },
        {
            "indicator": {"id": "EG.ELC.ACCS.ZS", "value": _NAME},
            "country": {"id": "EC", "value": "Ecuador"},
            "date": "2022",
            "value": 100,
        },
    ],
]

_ERROR = [{"message": [{"id": "175", "key": "Invalid format", "value": "The indicator was not found."}]}]

_SERIES_URL = "https://api.worldbank.org/v2/country/ECU/indicator/EG.ELC.ACCS.ZS"


@pytest.fixture(autouse=True)
def clear_cache():
    client._catalog_cache.clear()
    client._data_cache.clear()
    yield
    client._catalog_cache.clear()
    client._data_cache.clear()


async def test_search_matches_name_case_insensitively(httpx_mock):
    httpx_mock.add_response(
        url="https://api.worldbank.org/v2/indicator?source=2&format=json&per_page=5000",
        json=_CATALOG,
    )

    result = await client.search_indicadores(query="ELECTRICITY")

    assert result["total_catalogo"] == 2
    assert [i["indicador"] for i in result["indicadores"]] == ["EG.ELC.ACCS.ZS"]


async def test_get_indicador_sorts_ascending_and_drops_null_years(httpx_mock):
    httpx_mock.add_response(url=f"{_SERIES_URL}?format=json&per_page=1000", json=_SERIES)

    result = await client.get_indicador("EG.ELC.ACCS.ZS")

    assert result["serie"] == [{"anio": 2022, "valor": 100}, {"anio": 2024, "valor": 98.5}]
    assert result["anios_sin_dato"] == 1
    assert result["pais"] == "Ecuador"


async def test_get_indicador_passes_year_range(httpx_mock):
    httpx_mock.add_response(
        url=f"{_SERIES_URL}?format=json&per_page=1000&date=2020%3A2024", json=_SERIES
    )

    result = await client.get_indicador("EG.ELC.ACCS.ZS", desde=2020, hasta=2024)

    assert result["total_registros"] == 2


async def test_api_error_payload_raises(httpx_mock):
    httpx_mock.add_response(
        url="https://api.worldbank.org/v2/country/ECU/indicator/NOPE.X?format=json&per_page=1000",
        json=_ERROR,
    )

    with pytest.raises(ValueError, match="indicator was not found"):
        await client.get_indicador("NOPE.X")


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"indicador": "bad code!"}, "indicador inválido"),
        ({"indicador": "A.B", "pais": "../x"}, "país inválido"),
        ({"indicador": "A.B", "desde": 2020}, "juntos"),
        ({"indicador": "A.B", "desde": 2024, "hasta": 2020}, "mayor"),
    ],
)
async def test_input_validation(kwargs, match):
    with pytest.raises(ValueError, match=match):
        await client.get_indicador(**kwargs)

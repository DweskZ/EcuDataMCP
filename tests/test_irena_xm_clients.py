import pytest

from helpers import irena_client, xm_client

_FOLDER = irena_client._FOLDER
_TABLE_ID = "Country_ELECSTAT_2026_H2_PX.px"
_TABLE_URL = f"{_FOLDER}/{_TABLE_ID}"

_LISTING = [
    {"id": "Country_ELECSTAT_2025_H2_PX.px", "type": "t", "updated": "2025-09-01T00:00:00"},
    {"id": _TABLE_ID, "type": "t", "updated": "2026-09-28T17:56:28"},
    {"id": "Region_ELECSTAT_2026_H2_PX.px", "type": "t"},
]
_META = {
    "variables": [
        {"code": "Country/area", "values": ["ECU", "PER"], "valueTexts": ["Ecuador", "Peru"]},
    ]
}


def _cell(label_map):
    return {"category": {"index": {k: i for i, k in enumerate(label_map)}, "label": label_map}}


# 2 technologies x 2 data types x 1 connection x 2 years, row-major.
_DATA = {
    "id": ["Country/area", "Technology", "Data Type", "Grid connection", "Year"],
    "size": [1, 2, 2, 1, 2],
    "dimension": {
        "Country/area": _cell({"ECU": "Ecuador"}),
        "Technology": _cell({"0": "Renewable hydropower", "1": "Solar photovoltaic"}),
        "Data Type": _cell({"0": "Electricity Generation (GWh)", "1": "Electrical Installed Capacity (MW)"}),
        "Grid connection": _cell({"0": "All"}),
        "Year": _cell({"0": "2023", "1": "2024"}),
    },
    "value": [100.0, 110.0, 50.0, 55.0, None, 3.0, None, 84.27],
}


@pytest.fixture(autouse=True)
def clear_caches():
    for c in (irena_client._table_cache, irena_client._data_cache, xm_client._chunk_cache):
        c.clear()
    yield
    for c in (irena_client._table_cache, irena_client._data_cache, xm_client._chunk_cache):
        c.clear()


async def test_irena_picks_latest_table_and_filters(httpx_mock):
    httpx_mock.add_response(url=_FOLDER, json=_LISTING)
    httpx_mock.add_response(url=_TABLE_URL, method="GET", json=_META)
    httpx_mock.add_response(url=_TABLE_URL, method="POST", json=_DATA)

    result = await irena_client.get_electricidad(tecnologia="solar", tipo="capacidad")

    assert result["tabla"] == _TABLE_ID
    assert result["pais"] == "Ecuador"
    # null 2023 capacity is skipped; only 2024 solar capacity remains
    assert result["registros"] == [
        {
            "tecnologia": "Solar photovoltaic",
            "tipo": "capacidad_mw",
            "conexion": "All",
            "anio": 2024,
            "valor": 84.27,
        }
    ]


async def test_irena_year_range_and_generation(httpx_mock):
    httpx_mock.add_response(url=_FOLDER, json=_LISTING)
    httpx_mock.add_response(url=_TABLE_URL, method="GET", json=_META)
    httpx_mock.add_response(url=_TABLE_URL, method="POST", json=_DATA)

    result = await irena_client.get_electricidad(
        pais="ecuador", tecnologia="hydro", tipo="generacion", desde=2024, hasta=2024
    )

    assert [(r["anio"], r["valor"]) for r in result["registros"]] == [(2024, 110.0)]


async def test_irena_unknown_country_raises(httpx_mock):
    httpx_mock.add_response(url=_FOLDER, json=_LISTING)
    httpx_mock.add_response(url=_TABLE_URL, method="GET", json=_META)

    with pytest.raises(ValueError, match="País no encontrado"):
        await irena_client.get_electricidad(pais="Atlantis")


async def test_irena_dimension_names_are_case_insensitive(httpx_mock):
    renamed = {**_DATA, "id": [d.replace("Grid connection", "Grid Connection") for d in _DATA["id"]]}
    renamed["dimension"] = {
        ("Grid Connection" if k == "Grid connection" else k): v for k, v in _DATA["dimension"].items()
    }
    httpx_mock.add_response(url=_FOLDER, json=_LISTING)
    httpx_mock.add_response(url=_TABLE_URL, method="GET", json=_META)
    httpx_mock.add_response(url=_TABLE_URL, method="POST", json=renamed)

    result = await irena_client.get_electricidad(tecnologia="solar", tipo="capacidad")

    assert result["total_registros"] == 1


async def test_irena_missing_dimension_names_what_changed(httpx_mock):
    broken = {**_DATA, "id": [d.replace("Year", "Period") for d in _DATA["id"]]}
    broken["dimension"] = {("Period" if k == "Year" else k): v for k, v in _DATA["dimension"].items()}
    httpx_mock.add_response(url=_FOLDER, json=_LISTING)
    httpx_mock.add_response(url=_TABLE_URL, method="GET", json=_META)
    httpx_mock.add_response(url=_TABLE_URL, method="POST", json=broken)

    with pytest.raises(ValueError, match="no tiene la dimensión 'Year'"):
        await irena_client.get_electricidad()


def _xm_item(day, values):
    return {
        "Date": day,
        "HourlyEntities": [{"Id": "Enlace", "Values": {"code": "ECUADOR 230", **values}}],
    }


async def test_xm_daily_totals_skip_blank_hours_and_non_ecuador_links(httpx_mock):
    items = [
        _xm_item("2024-11-01", {"Hour01": "1000000", "Hour02": "", "Hour03": "500000"}),
        {
            "Date": "2024-11-01",
            "HourlyEntities": [{"Id": "Enlace", "Values": {"code": "VENEZUELA 230", "Hour01": "9"}}],
        },
    ]
    httpx_mock.add_response(url=xm_client._URL, method="POST", json={"Items": items})

    result = await xm_client.get_intercambio("2024-11-01", "2024-11-01")

    assert result["total_gwh"] == 1.5
    assert result["registros"] == [
        {"periodo": "2024-11-01", "enlace": "ECUADOR 230", "energia_gwh": 1.5, "horas_con_flujo": 2}
    ]


async def test_xm_reports_zero_for_days_without_flow_and_null_hours(httpx_mock):
    items = [_xm_item("2024-11-01", {"Hour01": "2000000", "Hour02": None})]
    httpx_mock.add_response(url=xm_client._URL, method="POST", json={"Items": items})

    result = await xm_client.get_intercambio("2024-11-01", "2024-11-03")

    assert result["total_por_periodo"] == {"2024-11-01": 2.0, "2024-11-02": 0.0, "2024-11-03": 0.0}
    assert [r["energia_gwh"] for r in result["registros"]] == [2.0, 0.0, 0.0]
    assert result["registros"][1]["horas_con_flujo"] == 0


async def test_xm_full_suspension_still_lists_every_month(httpx_mock):
    httpx_mock.add_response(url=xm_client._URL, method="POST", json={"Items": []})
    httpx_mock.add_response(url=xm_client._URL, method="POST", json={"Items": []})

    result = await xm_client.get_intercambio("2024-10-01", "2024-11-15", agregacion="mes")

    assert result["total_por_periodo"] == {"2024-10": 0.0, "2024-11": 0.0}
    assert result["total_gwh"] == 0.0


async def test_xm_splits_long_ranges_into_31_day_chunks(httpx_mock):
    httpx_mock.add_response(url=xm_client._URL, method="POST", json={"Items": []})
    httpx_mock.add_response(url=xm_client._URL, method="POST", json={"Items": []})

    await xm_client.get_intercambio("2024-10-01", "2024-11-15", agregacion="mes")

    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"desde": "2024-11-02", "hasta": "2024-11-01"}, "posterior"),
        ({"desde": "2020-01-01", "hasta": "2024-01-01"}, "366"),
        ({"desde": "nope", "hasta": "2024-01-01"}, "YYYY-MM-DD"),
        ({"desde": "2024-01-01", "hasta": "2024-01-02", "sentido": "x"}, "sentido"),
    ],
)
async def test_xm_input_validation(kwargs, match):
    with pytest.raises(ValueError, match=match):
        await xm_client.get_intercambio(**kwargs)

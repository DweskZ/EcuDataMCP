import pytest

from helpers import sut_powerbi_client as sut

_RESOURCE_KEY = "19718e1d-8f2d-4aa5-9528-80af28eaacfa"

# A trimmed but structurally real modelsAndExploration response: one
# section, one visual with a Column + a Measure + a HierarchyLevel field
# (the three shapes _spec_from_select_item must handle), plus a visual
# with no config (text box) and one whose HierarchyLevel is missing
# PropertyVariationSource (the real shape that crashed an earlier,
# throwaway version of this scraper on indiEstrategiasEmpleabilidad) --
# both must be skipped without raising.
_EXPLORATION_RESPONSE = {
    "models": [{"id": 1734940, "dbName": "57bf8b8e-ec0f-4a41-ad85-b5d6a69c9d2c"}],
    "exploration": {
        "reportId": 1720799,
        "sections": [
            {
                "displayName": "Evolución contratos",
                "visualContainers": [
                    {"config": None},
                    {
                        "config": (
                            '{"singleVisual":{"prototypeQuery":{'
                            '"From":[{"Name":"m","Entity":"Medidas","Type":0},'
                            '{"Name":"c","Entity":"Calendario_","Type":0},'
                            '{"Name":"p","Entity":"public contratos","Type":0}],'
                            '"Select":['
                            '{"Measure":{"Expression":{"SourceRef":{"Source":"m"}},'
                            '"Property":"Cantidad de Contratos"}},'
                            '{"Column":{"Expression":{"SourceRef":{"Source":"c"}},'
                            '"Property":"Mes"}},'
                            '{"HierarchyLevel":{"Expression":{"Hierarchy":{"Expression":'
                            '{"PropertyVariationSource":{"Expression":{"SourceRef":'
                            '{"Source":"p"}},"Name":"Variación","Property":"fecha_inicio_new"}},'
                            '"Hierarchy":"Jerarquía de fechas"}},"Level":"Año"}}'
                            "]}}}"
                        )
                    },
                    {
                        "config": (
                            '{"singleVisual":{"prototypeQuery":{'
                            '"From":[{"Name":"x","Entity":"Some Table","Type":0}],'
                            '"Select":[{"HierarchyLevel":{"Expression":{"Hierarchy":'
                            '{"Expression":{"SourceRef":{"Source":"x"}}}},"Level":"Año"}}]'
                            "}}}"
                        )
                    },
                ],
            }
        ],
    },
}


@pytest.fixture(autouse=True)
def clear_cache():
    sut._schema_cache.clear()
    yield
    sut._schema_cache.clear()


def test_list_indicadores_returns_eight_fixed_dashboards():
    indicadores = sut.list_indicadores()

    assert len(indicadores) == 8
    keys = {i["indicador"] for i in indicadores}
    assert "contratos" in keys
    indicadores[0]["indicador"] = "mutated"
    assert sut.list_indicadores()[0]["indicador"] != "mutated"


@pytest.mark.asyncio
async def test_get_indicador_schema_parses_column_measure_and_hierarchy(httpx_mock):
    httpx_mock.add_response(
        url=f"{sut._BASE}/public/reports/{_RESOURCE_KEY}/modelsAndExploration",
        json=_EXPLORATION_RESPONSE,
    )

    result = await sut.get_indicador_schema("contratos")

    assert result["indicador"] == "contratos"
    campos = set(result["campos"])
    assert "Medidas.Cantidad de Contratos [medida]" in campos
    assert "Calendario_.Mes" in campos
    assert "public contratos.fecha_inicio_new [Año]" in campos
    # The malformed hierarchy visual (no PropertyVariationSource) and the
    # config-less visual must not crash the fetch or appear as fields.
    assert not any("Some Table" in c for c in campos)


@pytest.mark.asyncio
async def test_get_indicador_schema_rejects_unknown_indicador():
    with pytest.raises(ValueError, match="no reconocido"):
        await sut.get_indicador_schema("no-existe")


@pytest.mark.asyncio
async def test_get_indicador_schema_caches_bootstrap(httpx_mock):
    httpx_mock.add_response(
        url=f"{sut._BASE}/public/reports/{_RESOURCE_KEY}/modelsAndExploration",
        json=_EXPLORATION_RESPONSE,
    )

    first = await sut.get_indicador_schema("contratos")
    second = await sut.get_indicador_schema("contratos")

    assert first == second
    assert len(httpx_mock.get_requests()) == 1


def test_decode_dsr_matches_ground_truth_read_off_the_live_dashboard():
    # Real (trimmed) response shape for the "Evolución mensual" query,
    # decoded values cross-checked 2026-08-30 against numbers read
    # directly off the live Power BI dashboard's own "Show as a table"
    # export (enero 2015 = 92,306; febrero 2015 = 55,571).
    data = {
        "descriptor": {
            "Select": [
                {"Value": "M0", "Name": "Medidas.Cantidad de Contratos"},
                {"Value": "G0", "Name": "Calendario_.Mes"},
                {"Value": "G1", "Name": "public contratos.fecha_inicio_new.Variación.Jerarquía de fechas.Año"},
            ]
        },
        "dsr": {
            "DS": [
                {
                    "PH": [
                        {
                            "DM0": [
                                {
                                    "S": [
                                        {"N": "G0", "T": 1, "DN": "D0"},
                                        {"N": "G1", "T": 4},
                                        {"N": "M0", "T": 4},
                                    ],
                                    "C": [0, 2015, 92306],
                                },
                                {"C": [1, 55571], "R": 2},
                                # Row 3: month resets (new schema-order value
                                # for G0) but year repeats -- R=2 keeps year,
                                # C supplies month index + count.
                                {"C": [2, 56583], "R": 2},
                            ]
                        }
                    ],
                    "ValueDicts": {"D0": ["ene", "feb", "mar"]},
                }
            ]
        },
    }

    rows = sut._decode_dsr(data)

    assert rows == [
        {
            "Calendario_.Mes": "ene",
            "public contratos.fecha_inicio_new.Variación.Jerarquía de fechas.Año": 2015,
            "Medidas.Cantidad de Contratos": 92306,
        },
        {
            "Calendario_.Mes": "feb",
            "public contratos.fecha_inicio_new.Variación.Jerarquía de fechas.Año": 2015,
            "Medidas.Cantidad de Contratos": 55571,
        },
        {
            "Calendario_.Mes": "mar",
            "public contratos.fecha_inicio_new.Variación.Jerarquía de fechas.Año": 2015,
            "Medidas.Cantidad de Contratos": 56583,
        },
    ]


def test_decode_dsr_null_mask_sets_value_to_none():
    data = {
        "descriptor": {"Select": [{"Value": "G0", "Name": "campo.a"}, {"Value": "M0", "Name": "campo.b"}]},
        "dsr": {
            "DS": [
                {
                    "PH": [
                        {
                            "DM0": [
                                {"S": [{"N": "G0", "T": 1}, {"N": "M0", "T": 4}], "C": [1, 10]},
                                # Ø=1 -> bit 0 (G0) is null this row; only
                                # M0's new value (20) appears in C.
                                {"C": [20], "Ø": 1},
                            ]
                        }
                    ],
                    "ValueDicts": {},
                }
            ]
        },
    }

    rows = sut._decode_dsr(data)

    assert rows[1] == {"campo.a": None, "campo.b": 20}


@pytest.mark.asyncio
async def test_query_indicador_rejects_unknown_campo(httpx_mock):
    httpx_mock.add_response(
        url=f"{sut._BASE}/public/reports/{_RESOURCE_KEY}/modelsAndExploration",
        json=_EXPLORATION_RESPONSE,
    )

    with pytest.raises(ValueError, match="no existe en 'contratos'"):
        await sut.query_indicador("contratos", campos=["no.existe"])


@pytest.mark.asyncio
async def test_query_indicador_rejects_measure_as_filter(httpx_mock):
    httpx_mock.add_response(
        url=f"{sut._BASE}/public/reports/{_RESOURCE_KEY}/modelsAndExploration",
        json=_EXPLORATION_RESPONSE,
    )

    with pytest.raises(ValueError, match="columna, no una medida"):
        await sut.query_indicador(
            "contratos",
            campos=["Calendario_.Mes"],
            filtros={"Medidas.Cantidad de Contratos [medida]": "5"},
        )


@pytest.mark.asyncio
async def test_query_indicador_sends_resource_key_header_and_decodes_response(httpx_mock):
    httpx_mock.add_response(
        url=f"{sut._BASE}/public/reports/{_RESOURCE_KEY}/modelsAndExploration",
        json=_EXPLORATION_RESPONSE,
    )
    query_response = {
        "results": [
            {
                "result": {
                    "data": {
                        "descriptor": {"Select": [{"Value": "G0", "Name": "Calendario_.Mes"}]},
                        "dsr": {
                            "DS": [
                                {
                                    "PH": [{"DM0": [{"S": [{"N": "G0", "T": 1, "DN": "D0"}], "C": [0]}]}],
                                    "ValueDicts": {"D0": ["ene"]},
                                }
                            ]
                        },
                    }
                }
            }
        ]
    }
    httpx_mock.add_response(
        method="POST",
        url=f"{sut._BASE}/public/reports/querydata?synchronous=true",
        json=query_response,
    )

    result = await sut.query_indicador("contratos", campos=["Calendario_.Mes"])

    assert result["filas"] == [{"Calendario_.Mes": "ene"}]
    requests = httpx_mock.get_requests(url=f"{sut._BASE}/public/reports/querydata?synchronous=true")
    assert len(requests) == 1
    assert requests[0].headers["x-powerbi-resourcekey"] == _RESOURCE_KEY


@pytest.mark.asyncio
async def test_query_indicador_returns_empty_rows_when_response_has_no_data(httpx_mock):
    httpx_mock.add_response(
        url=f"{sut._BASE}/public/reports/{_RESOURCE_KEY}/modelsAndExploration",
        json=_EXPLORATION_RESPONSE,
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{sut._BASE}/public/reports/querydata?synchronous=true",
        json={"results": [{"result": {}}]},
    )

    result = await sut.query_indicador("contratos", campos=["Calendario_.Mes"])

    assert result["filas"] == []


# denuncias_publico/encuentra_empleo ship a report layout where
# visualContainers carry no "config" at all (id/x/y/z/width/height/
# objectName only) -- confirmed live 2026-08-31. _MANUAL_CAMPOS is the
# recovery path: fields captured by driving the real dashboard in a
# browser, merged on top of whatever _collect_fields finds (nothing, for
# these two). An exploration response shaped that way is the realistic
# fixture here, not the config-bearing one used above.
_EMPTY_VISUALCONTAINER_EXPLORATION = {
    "models": [{"id": 718086, "dbName": "5fff07ab-7193-4a8e-8d6d-70e1cd993ea3"}],
    "exploration": {
        "reportId": 619692,
        "sections": [
            {
                "displayName": "Denuncias",
                "visualContainers": [
                    {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0, "width": 0.0, "height": 0.0, "objectName": "abc"}
                ],
            }
        ],
    },
}


@pytest.mark.asyncio
async def test_get_indicador_schema_falls_back_to_manual_campos_when_layout_has_no_config(httpx_mock):
    httpx_mock.add_response(
        url=f"{sut._BASE}/public/reports/{sut._INDICADORES_BY_KEY['denuncias_publico']['resource_key']}/modelsAndExploration",
        json=_EMPTY_VISUALCONTAINER_EXPLORATION,
    )

    result = await sut.get_indicador_schema("denuncias_publico")

    assert "REGISTROS.Cantidad denuncias [medida]" in result["campos"]
    assert "REGISTROS.5.-Motivo de la Denuncia" in result["campos"]


def test_build_select_item_for_aggregated_sum_kind():
    spec = sut._MANUAL_CAMPOS["encuentra_empleo"]["CONSOLIDADO.Número de Personas [medida]"]

    item = sut._build_select_item(spec, "c")

    assert item["Aggregation"]["Function"] == 0
    assert item["Aggregation"]["Expression"]["Column"]["Property"] == "Número de Personas"
    assert item["Name"] == "Sum(CONSOLIDADO.Número de Personas)"


@pytest.mark.asyncio
async def test_query_indicador_encuentra_empleo_uses_aggregation_and_decodes_rows(httpx_mock):
    resource_key = sut._INDICADORES_BY_KEY["encuentra_empleo"]["resource_key"]
    empty_exploration = {
        "models": [{"id": 1729056, "dbName": "671ccb31-bf9d-4651-ac16-8e553c0428fe"}],
        "exploration": {"reportId": 1715110, "sections": []},
    }
    httpx_mock.add_response(
        url=f"{sut._BASE}/public/reports/{resource_key}/modelsAndExploration",
        json=empty_exploration,
    )
    query_response = {
        "results": [
            {
                "result": {
                    "data": {
                        "descriptor": {
                            "Select": [
                                {"Value": "G0", "Name": "CONSOLIDADO.Encuentra Empleo"},
                                {"Value": "M0", "Name": "Sum(CONSOLIDADO.Número de Personas)"},
                            ]
                        },
                        "dsr": {
                            "DS": [
                                {
                                    "PH": [
                                        {
                                            "DM0": [
                                                {
                                                    "S": [
                                                        {"N": "G0", "T": 1, "DN": "D0"},
                                                        {"N": "M0", "T": 4},
                                                    ],
                                                    "C": [0, 26033],
                                                }
                                            ]
                                        }
                                    ],
                                    "ValueDicts": {"D0": ["REGISTRADOS"]},
                                }
                            ]
                        },
                    }
                }
            }
        ]
    }
    httpx_mock.add_response(
        method="POST",
        url=f"{sut._BASE}/public/reports/querydata?synchronous=true",
        json=query_response,
    )

    result = await sut.query_indicador(
        "encuentra_empleo",
        campos=["CONSOLIDADO.Encuentra Empleo", "CONSOLIDADO.Número de Personas [medida]"],
    )

    assert result["filas"] == [
        {"CONSOLIDADO.Encuentra Empleo": "REGISTRADOS", "Sum(CONSOLIDADO.Número de Personas)": 26033}
    ]
    request = httpx_mock.get_requests(url=f"{sut._BASE}/public/reports/querydata?synchronous=true")[0]
    sent = request.content.decode("utf-8")
    assert '"Function": 0' in sent or '"Function":0' in sent

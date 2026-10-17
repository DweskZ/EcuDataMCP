import json

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


# --- Consejo de la Judicatura (second cluster, newer report layouts) -------

_JUD_KEY = "789ae560-e736-437e-9aef-85564a353257"
_JUD_BASE = sut._JUDICATURA_BASE
_PBIR_DOC = (
    '{"pages":{"pages":[{"content":{"visuals":[{"query":{"queryState":{"Rows":'
    '{"projections":['
    '{"field":{"Column":{"Expression":{"SourceRef":{"Entity":"CUB EST_PROD"}},"Property":"Juez"}}},'
    '{"field":{"Measure":{"Expression":{"SourceRef":{"Entity":"CUB EST_PROD"}},"Property":"Promedio"}}},'
    '{"field":{"Aggregation":{"Expression":{"Column":{"Expression":{"SourceRef":'
    '{"Entity":"CUB EST_PROD"}},"Property":"Tramite"}},"Function":0}}},'
    '{"field":{"Aggregation":{"Expression":{"Column":{"Expression":{"SourceRef":'
    '{"Entity":"CUB EST_PROD"}},"Property":"Corte"}},"Function":3}}},'
    '{"field":{"Column":{"Expression":{"SourceRef":{"Entity":"LocalDateTable_x"}},"Property":"Año"}}}'
    "]}}}}]}}]}}"
)
_JUD_EXPLORATION = {
    "models": [{"id": 4541304, "dbName": "f8d9cd7d-d1fb-4af6-8219-7ecd87a5d32c"}],
    "exploration": {
        "reportId": "4577594",
        "sections": [{"visualContainers": [{"id": 1, "objectName": "abc"}]}],
        "explorationContent": {"explorationDocument": _PBIR_DOC},
    },
}


def test_list_indicadores_defaults_to_sut_and_filters_by_fuente():
    assert len(sut.list_indicadores()) == 8
    assert all(i["fuente"] == "sut" for i in sut.list_indicadores())
    jud = sut.list_indicadores("judicatura")
    assert len(jud) == 10
    assert {"audiencias", "productividad_jueces", "supa"} <= {i["indicador"] for i in jud}
    assert all(i["base"] == _JUD_BASE for i in jud)
    with pytest.raises(ValueError, match="Fuente 'x'"):
        sut.list_indicadores("x")


@pytest.mark.asyncio
async def test_judicatura_schema_uses_its_own_cluster_and_falls_back_to_entity_walk(httpx_mock):
    httpx_mock.add_response(
        url=f"{_JUD_BASE}/public/reports/{_JUD_KEY}/modelsAndExploration",
        json=_JUD_EXPLORATION,
    )

    result = await sut.get_indicador_schema("productividad_jueces", "judicatura")

    assert result["fuente"] == "judicatura"
    # An aggregated column also stays queryable as a plain column (filters);
    # unsupported aggregation codes (Corte, Function 3) and hidden
    # LocalDateTable_ entities add nothing beyond that plain column.
    assert result["campos"] == [
        "CUB EST_PROD.Corte",
        "CUB EST_PROD.Juez",
        "CUB EST_PROD.Promedio [medida]",
        "CUB EST_PROD.Tramite",
        "CUB EST_PROD.Tramite [suma]",
    ]


@pytest.mark.asyncio
async def test_indicador_is_scoped_to_its_fuente():
    with pytest.raises(ValueError, match="no reconocido en la fuente 'sut'"):
        await sut.get_indicador_schema("audiencias")
    with pytest.raises(ValueError, match="no reconocido en la fuente 'judicatura'"):
        await sut.get_indicador_schema("contratos", "judicatura")


@pytest.mark.asyncio
async def test_judicatura_query_posts_to_its_cluster_with_aggregation_and_filter(httpx_mock):
    httpx_mock.add_response(
        url=f"{_JUD_BASE}/public/reports/{_JUD_KEY}/modelsAndExploration",
        json=_JUD_EXPLORATION,
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{_JUD_BASE}/public/reports/querydata?synchronous=true",
        json={
            "results": [
                {
                    "result": {
                        "data": {
                            "descriptor": {
                                "Select": [
                                    {"Value": "G0", "Name": "CUB EST_PROD.Juez"},
                                    {"Value": "M0", "Name": "suma(CUB EST_PROD.Tramite)"},
                                ]
                            },
                            "dsr": {
                                "DS": [
                                    {
                                        "PH": [
                                            {
                                                "DM0": [
                                                    {
                                                        "S": [{"N": "G0", "T": 1}, {"N": "M0", "T": 4}],
                                                        "C": ["ANA", 12],
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                        }
                    }
                }
            ]
        },
    )

    result = await sut.query_indicador(
        "productividad_jueces",
        ["CUB EST_PROD.Juez", "CUB EST_PROD.Tramite [suma]"],
        filtros={"CUB EST_PROD.Juez": "ANA"},
        fuente="judicatura",
    )

    assert result["filas"] == [{"CUB EST_PROD.Juez": "ANA", "suma(CUB EST_PROD.Tramite)": 12}]
    request = httpx_mock.get_requests(url=f"{_JUD_BASE}/public/reports/querydata?synchronous=true")[0]
    assert request.headers["x-powerbi-resourcekey"] == _JUD_KEY
    select = json.loads(request.content)["queries"][0]["Query"]["Commands"][0][
        "SemanticQueryDataShapeCommand"
    ]["Query"]["Select"]
    assert select[1]["Aggregation"]["Function"] == 0


def test_decode_dsr_single_column_group_entries():
    data = {
        "descriptor": {"Select": [{"Value": "G0", "Name": "t.Canton"}]},
        "dsr": {
            "DS": [
                {
                    "PH": [
                        {
                            "DM0": [
                                {"S": [{"N": "G0", "T": 1}], "G0": "A"},
                                {"G0": "B"},
                            ]
                        }
                    ]
                }
            ]
        },
    }

    assert sut._decode_dsr(data) == [{"t.Canton": "A"}, {"t.Canton": "B"}]


def test_select_item_aggregation_becomes_suma_field():
    spec = sut._spec_from_select_item(
        {
            "Aggregation": {
                "Expression": {"Column": {"Expression": {"SourceRef": {"Source": "a"}}, "Property": "Contador"}},
                "Function": 0,
            }
        },
        {"a": "CUB EST_CUB_AUDIENCIAS"},
    )

    assert spec["kind"] == "aggregation"
    assert sut._field_label(spec["entity"], spec["property"], spec["kind"], None, spec["function"]) == (
        "CUB EST_CUB_AUDIENCIAS.Contador [suma]"
    )


def test_literal_value_escapes_single_quotes_and_defaults_to_string():
    assert sut._literal_value({"kind": "column"}, "O'Brien") == "'O''Brien'"
    assert sut._literal_value({"kind": "column"}, "2024") == "'2024'"


def test_literal_value_emits_typed_literals_from_data_type():
    assert sut._literal_value({"data_type": "int"}, "2024") == "2024L"
    assert sut._literal_value({"data_type": "decimal"}, "1.5") == "1.5D"
    assert sut._literal_value({"data_type": "bool"}, "True") == "true"
    # unparsable value for a numeric column falls back to a safe string
    assert sut._literal_value({"data_type": "int"}, "abc'") == "'abc" + "''" + "'"


def test_spec_from_select_item_reads_named_data_type_when_present():
    col = {"Expression": {"SourceRef": {"Source": "a"}}, "Property": "Anio"}
    typed = {"Column": {**col, "DataType": "Int64"}}
    assert sut._spec_from_select_item(typed, {"a": "E"})["data_type"] == "int"
    assert "data_type" not in sut._spec_from_select_item({"Column": col}, {"a": "E"})


def _where_literal(httpx_mock):
    sent = json.loads(httpx_mock.get_requests()[-1].content)
    query = sent["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]["Query"]
    return query["Where"][0]["Condition"]["In"]["Values"][0][0]["Literal"]["Value"]


def _setup_empty_query(httpx_mock):
    httpx_mock.add_response(
        url=f"{sut._BASE}/public/reports/{_RESOURCE_KEY}/modelsAndExploration",
        json=_EXPLORATION_RESPONSE,
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{sut._BASE}/public/reports/querydata?synchronous=true",
        json={"results": [{"result": {}}]},
    )


@pytest.mark.asyncio
async def test_query_indicador_escapes_filter_quote_and_clamps_limite(httpx_mock):
    _setup_empty_query(httpx_mock)

    result = await sut.query_indicador(
        "contratos",
        campos=["Calendario_.Mes"],
        filtros={"Calendario_.Mes": "O'Higgins"},
        limite=10_000_000,
    )

    request = httpx_mock.get_requests(url=f"{sut._BASE}/public/reports/querydata?synchronous=true")[0]
    body = json.loads(request.content)
    command = body["queries"][0]["Query"]["Commands"][0]["SemanticQueryDataShapeCommand"]
    literal = command["Query"]["Where"][0]["Condition"]["In"]["Values"][0][0]["Literal"]["Value"]
    assert literal == "'O''Higgins'"
    assert command["Binding"]["DataReduction"]["Primary"]["Window"]["Count"] == sut._MAX_ROW_LIMIT
    assert result["limite"] == sut._MAX_ROW_LIMIT
    assert result["truncado"] is False


@pytest.mark.asyncio
async def test_query_indicador_raises_on_power_bi_error_body(httpx_mock):
    # Power BI rejects a query with HTTP 200 and an error object where the
    # rows would be; that must not be reported as "0 rows".
    httpx_mock.add_response(
        url=f"{sut._BASE}/public/reports/{_RESOURCE_KEY}/modelsAndExploration",
        json=_EXPLORATION_RESPONSE,
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{sut._BASE}/public/reports/querydata?synchronous=true",
        json={"error": {"code": "InvalidQuery", "message": "Column not found"}},
    )

    with pytest.raises(ValueError, match="Power BI rechazó la consulta: Column not found"):
        await sut.query_indicador("contratos", campos=["Calendario_.Mes"])


@pytest.mark.asyncio
async def test_query_indicador_flags_truncation_when_window_fills(httpx_mock):
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
                                    "PH": [
                                        {
                                            "DM0": [
                                                {"S": [{"N": "G0", "T": 1, "DN": "D0"}], "C": [0]},
                                                {"C": [1]},
                                            ]
                                        }
                                    ],
                                    "ValueDicts": {"D0": ["ene", "feb"]},
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

    result = await sut.query_indicador("contratos", campos=["Calendario_.Mes"], limite=2)

    assert [row["Calendario_.Mes"] for row in result["filas"]] == ["ene", "feb"]
    assert result["truncado"] is True


@pytest.mark.asyncio
async def test_untyped_numeric_filter_with_no_rows_adds_hint(httpx_mock):
    _setup_empty_query(httpx_mock)

    result = await sut.query_indicador("contratos", campos=["Calendario_.Mes"], filtros={"Calendario_.Mes": "2024"})

    assert result["filas"] == []
    assert "numérica" in result["aviso"]
    assert _where_literal(httpx_mock) == "'2024'"


@pytest.mark.asyncio
async def test_typed_filter_emits_typed_literal_and_no_hint(httpx_mock):
    _setup_empty_query(httpx_mock)
    boot = await sut._get_bootstrap(_RESOURCE_KEY, "contratos")
    boot["campos"]["Calendario_.Mes"]["data_type"] = "int"

    result = await sut.query_indicador("contratos", campos=["Calendario_.Mes"], filtros={"Calendario_.Mes": "2024"})

    assert "aviso" not in result
    assert _where_literal(httpx_mock) == "2024L"

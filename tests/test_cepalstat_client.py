import pytest

from helpers import cepalstat_client as client

# Trimmed but structurally faithful excerpts of the real
# api-cepalstat.cepal.org responses (confirmed live 2026-09-10):
# thematic-tree is a nested theme/area/indicator tree; indicator/{id}/data
# returns opaque dim_<dimension_id> keys per row, decoded against that same
# response's own "dimensions" catalog.
_TREE_JSON = {
    "header": {},
    "body": {
        "name": "Clasificación temática general",
        "order": 0,
        "theme_id": 27,
        "children": [
            {
                "name": "Demográficos y sociales",
                "area_id": 1,
                "children": [
                    {
                        "name": "Población",
                        "area_id": 2,
                        "children": [
                            {"name": "Población total, según sexo", "indicator_id": 4788},
                            {"name": "Tasa de crecimiento de la población", "indicator_id": 36},
                        ],
                    }
                ],
            },
            {
                "name": "Económicos",
                "area_id": 3,
                "children": [
                    {"name": "Pobreza monetaria", "indicator_id": 99},
                ],
            },
        ],
    },
    "footer": {},
}

_DIMENSIONS_JSON = {
    "header": {},
    "body": {
        "dimensions": [
            {
                "id": 208,
                "name": "País__ESTANDAR",
                "members": [
                    {"name": "Ecuador", "id": 229},
                    {"name": "Perú", "id": 230},
                ],
            },
            {"id": 29117, "name": "Años__ESTANDAR", "members": [{"name": "1950", "id": 68109}]},
        ]
    },
    "footer": {},
}

_DATA_JSON = {
    "header": {},
    "body": {
        "metadata": {"indicator_id": 4788, "indicator_name": "Población total, según sexo"},
        "data": [
            {"value": "3516.8", "source_id": 6547, "notes_ids": "13637", "iso3": "ECU",
             "dim_208": 229, "dim_29117": 68109},
        ],
        "dimensions": [
            {
                "id": 208,
                "name": "País__ESTANDAR",
                "members": [{"name": "Ecuador", "id": 229}, {"name": "Perú", "id": 230}],
            },
            {"id": 29117, "name": "Años__ESTANDAR", "members": [{"name": "1950", "id": 68109}]},
        ],
        "sources": [{"id": 6547, "description": "CELADE - CEPAL"}],
        "footnotes": [{"id": 13637, "description": "El total no siempre coincide."}],
    },
    "footer": {},
}


@pytest.fixture(autouse=True)
def clear_cache():
    client._tree_cache.clear()
    client._dimensions_cache.clear()
    yield
    client._tree_cache.clear()
    client._dimensions_cache.clear()


async def test_search_indicadores_flattens_tree_with_area_breadcrumb(httpx_mock):
    httpx_mock.add_response(
        url=client._build_url("/thematic-tree", lang="es"), json=_TREE_JSON
    )

    result = await client.search_indicadores(query="poblacion total")

    assert result["total_catalogo"] == 3
    assert result["total"] == 1
    ind = result["indicadores"][0]
    assert ind["indicator_id"] == 4788
    assert ind["area"] == (
        "Clasificación temática general > Demográficos y sociales > Población"
    )


async def test_search_indicadores_matches_on_area_breadcrumb_too(httpx_mock):
    httpx_mock.add_response(
        url=client._build_url("/thematic-tree", lang="es"), json=_TREE_JSON
    )

    result = await client.search_indicadores(query="economicos")

    assert result["total"] == 1
    assert result["indicadores"][0]["indicator_id"] == 99


async def test_search_indicadores_empty_query_returns_everything(httpx_mock):
    httpx_mock.add_response(
        url=client._build_url("/thematic-tree", lang="es"), json=_TREE_JSON
    )

    result = await client.search_indicadores()

    assert result["total"] == result["total_catalogo"] == 3


async def test_get_indicador_filters_to_ecuador_and_decodes_dimensions(httpx_mock):
    httpx_mock.add_response(
        url=client._build_url("/indicator/4788/dimensions", lang="es"), json=_DIMENSIONS_JSON
    )
    httpx_mock.add_response(
        url=client._build_url("/indicator/4788/data", lang="es", format="json", members=229),
        json=_DATA_JSON,
    )

    result = await client.get_indicador(4788, pais="Ecuador")

    assert result["pais_filtrado"] == "Ecuador"
    assert result["total_registros"] == 1
    record = result["registros"][0]
    assert record["valor"] == "3516.8"
    # The "__ESTANDAR" classification-scheme suffix is stripped for
    # readability; the member id is decoded into its name.
    assert record["País"] == "Ecuador"
    assert record["Años"] == "1950"
    assert record["iso3"] == "ECU"
    assert "notes_ids" not in record
    assert result["fuentes"][0]["description"] == "CELADE - CEPAL"
    assert result["notas"][0]["description"] == "El total no siempre coincide."


async def test_get_indicador_accent_insensitive_country_match(httpx_mock):
    httpx_mock.add_response(
        url=client._build_url("/indicator/4788/dimensions", lang="es"), json=_DIMENSIONS_JSON
    )
    httpx_mock.add_response(
        url=client._build_url("/indicator/4788/data", lang="es", format="json", members=230),
        json=_DATA_JSON,
    )

    result = await client.get_indicador(4788, pais="peru")

    # Labelled with CEPALSTAT's own member name, not the user's spelling.
    assert result["pais_filtrado"] == "Perú"


async def test_get_indicador_ambiguous_partial_country_match_raises(httpx_mock):
    dimensions = {
        "header": {},
        "body": {
            "dimensions": [
                {
                    "id": 208,
                    "name": "País__ESTANDAR",
                    "members": [
                        {"name": "Guinea", "id": 1},
                        {"name": "Guinea Ecuatorial", "id": 2},
                        {"name": "Ecuador", "id": 229},
                    ],
                }
            ]
        },
        "footer": {},
    }
    httpx_mock.add_response(
        url=client._build_url("/indicator/4788/dimensions", lang="es"), json=dimensions
    )

    with pytest.raises(ValueError, match="Guinea; Guinea Ecuatorial"):
        await client.get_indicador(4788, pais="guin")


def test_find_pais_member_prefers_exact_match_over_partial_ones():
    dimensions = [
        {
            "name": "País",
            "members": [{"name": "Guinea", "id": 1}, {"name": "Guinea Ecuatorial", "id": 2}],
        }
    ]

    assert client._find_pais_member(dimensions, "Guinea")["id"] == 1
    assert client._find_pais_member(dimensions, "ecuatorial")["id"] == 2
    assert client._find_pais_member(dimensions, "Narnia") is None


async def test_get_indicador_unknown_country_raises(httpx_mock):
    httpx_mock.add_response(
        url=client._build_url("/indicator/4788/dimensions", lang="es"), json=_DIMENSIONS_JSON
    )

    with pytest.raises(ValueError, match="4788"):
        await client.get_indicador(4788, pais="Narnia")


async def test_get_indicador_empty_pais_skips_dimensions_lookup_and_filter(httpx_mock):
    unfiltered = {
        **_DATA_JSON,
        "body": {**_DATA_JSON["body"], "data": []},
    }
    httpx_mock.add_response(
        url=client._build_url("/indicator/4788/data", lang="es", format="json"),
        json=unfiltered,
    )

    result = await client.get_indicador(4788, pais="")

    assert result["pais_filtrado"] is None
    # No /dimensions call should have been made at all -- asserted
    # implicitly: httpx_mock would raise on an unmatched request if one
    # were attempted, since only the /data route above was registered.


async def test_thematic_tree_is_cached_across_calls(httpx_mock):
    httpx_mock.add_response(
        url=client._build_url("/thematic-tree", lang="es"), json=_TREE_JSON
    )

    first = await client.search_indicadores(query="poblacion")
    second = await client.search_indicadores(query="pobreza")

    assert first["total_catalogo"] == second["total_catalogo"] == 3


_BOLIVIA_DIMENSIONS = [
    {
        "name": "País__ESTANDAR",
        "members": [
            {"name": "Bolivia (Estado Plurinacional de)", "id": 221},
            {"name": "Mercado Común del Sur (MERCOSUR)", "id": 31809},
            {
                "name": "Mercado Común del Sur (MERCOSUR), Bolivia (Estado Plurinacional de) y Chile",
                "id": 46573,
            },
            {"name": "Perú", "id": 244},
            {"name": "Trinidad y Tabago", "id": 300},
            {"name": "Guinea", "id": 1},
            {"name": "Guinea Ecuatorial", "id": 2},
        ],
    }
]


@pytest.mark.parametrize("pais", ["Bolivia", "bolivia", "BOL", "Bolivia (Estado Plurinacional de)"])
def test_find_pais_member_bolivia_ignores_aggregates_that_mention_it(pais):
    assert client._find_pais_member(_BOLIVIA_DIMENSIONS, pais)["id"] == 221


@pytest.mark.parametrize("pais", ["Peru", "perú", "PER"])
def test_find_pais_member_peru_accent_and_iso3(pais):
    assert client._find_pais_member(_BOLIVIA_DIMENSIONS, pais)["id"] == 244


def test_find_pais_member_aggregate_only_when_named():
    assert client._find_pais_member(_BOLIVIA_DIMENSIONS, "MERCOSUR")["id"] == 31809
    assert client._find_pais_member(_BOLIVIA_DIMENSIONS, "Mercado Común del Sur")["id"] == 31809
    full = "Mercado Común del Sur (MERCOSUR), Bolivia (Estado Plurinacional de) y Chile"
    assert client._find_pais_member(_BOLIVIA_DIMENSIONS, full)["id"] == 46573


def test_find_pais_member_keeps_real_countries_with_y_in_the_name():
    assert client._find_pais_member(_BOLIVIA_DIMENSIONS, "tabago")["id"] == 300


def test_find_pais_member_genuine_ambiguity_lists_only_real_candidates():
    with pytest.raises(ValueError, match="Guinea; Guinea Ecuatorial") as exc:
        client._find_pais_member(_BOLIVIA_DIMENSIONS, "guin")
    assert "MERCOSUR" not in str(exc.value)


def test_find_pais_member_ambiguous_aggregates_when_only_they_match():
    dims = [
        {
            "name": "País",
            "members": [
                {"name": "Grupo Sur, Bolivia y Chile", "id": 1},
                {"name": "Grupo Sur, Perú y Chile", "id": 2},
            ],
        }
    ]
    with pytest.raises(ValueError, match="ambiguo"):
        client._find_pais_member(dims, "grupo sur")


async def test_get_indicador_flags_possible_series_break(httpx_mock):
    dims = {
        "header": {},
        "body": {"dimensions": _BOLIVIA_DIMENSIONS + [{"name": "Años", "members": []}]},
        "footer": {},
    }
    httpx_mock.add_response(
        url=client._build_url("/indicator/4891/dimensions", lang="es"), json=dims
    )
    data = {
        "header": {},
        "body": {
            "metadata": {"unit": "Porcentaje sobre el total de hogares"},
            "dimensions": [
                {"id": 208, "name": "País__ESTANDAR", "members": [{"id": 244, "name": "Perú"}]},
                {
                    "id": 29117,
                    "name": "Años__ESTANDAR",
                    "members": [{"id": 1, "name": "2022"}, {"id": 2, "name": "2023"}],
                },
            ],
            "data": [
                {"value": "55.2", "dim_208": 244, "dim_29117": 1},
                {"value": "89.6", "dim_208": 244, "dim_29117": 2},
            ],
        },
        "footer": {},
    }
    httpx_mock.add_response(
        url=client._build_url("/indicator/4891/data", lang="es", format="json", members=244),
        json=data,
    )

    result = await client.get_indicador(4891, pais="PER")

    (quiebre,) = result["posible_quiebre_serie"]
    assert (quiebre["desde"], quiebre["hasta"], quiebre["salto_pp"]) == (2022, 2023, 34.4)


def test_detectar_quiebres_ignores_small_moves_and_non_percentage_units():
    rows = [
        {"País": "Perú", "Años": "2022", "valor": "50"},
        {"País": "Perú", "Años": "2023", "valor": "60"},
    ]
    assert client._detectar_quiebres(rows, "Porcentaje") == []
    big = [{**rows[0], "valor": "10"}, {**rows[1], "valor": "90"}]
    assert client._detectar_quiebres(big, "Millones de dólares") == []
    assert len(client._detectar_quiebres(big, "Porcentaje")) == 1

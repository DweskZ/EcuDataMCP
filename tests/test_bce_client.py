import pytest

from helpers import bce_client
from helpers.cache import TtlCache

_TREE = [
    {"desc_clasificador": "1.  SECCION A", "id_grupo": None, "num_nivel": 1},
    {"desc_clasificador": "1.1  Subseccion A1", "id_grupo": None, "num_nivel": 2},
    {"desc_clasificador": "1.1.1  Grupo Uno", "id_grupo": 10, "num_nivel": 3},
    {"desc_clasificador": "1.2  Subseccion A2 (con grupo propio)", "id_grupo": 11, "num_nivel": 2},
    {"desc_clasificador": "2.  SECCION B", "id_grupo": None, "num_nivel": 1},
    {"desc_clasificador": "2.1  Mercado Laboral", "id_grupo": 20, "num_nivel": 2},
]

_BUNDLE_10 = {
    "context": {"id_grupo": 10, "nom_grupo": "Grupo Uno"},
    "frecuencias": ["Mensual", "Anual"],
    "unidades": {
        "Mensual": ["Millones de USD", "Numero"],
        "Anual": ["Millones de USD"],
    },
    "range": {"minYm": "2020-01", "maxYm": "2026-06"},
    "range_by_freq": {
        "Mensual": {"minYm": "2020-01", "maxYm": "2026-06"},
        "Anual": {"minYm": "2020", "maxYm": "2025"},
    },
    "rows": [
        {"tipo": "Cabeceras", "label": "TOTAL"},
        {"tipo": "Series", "label": "Serie A", "ruta": "total\\serie a"},
    ],
}

_BUNDLE_11 = {
    "context": {"id_grupo": 11, "nom_grupo": "Subseccion A2"},
    "frecuencias": ["Mensual"],
    "unidades": {"Mensual": ["Numero"]},
    "range": {"minYm": "2020-01", "maxYm": "2026-06"},
    "range_by_freq": {"Mensual": {"minYm": "2020-01", "maxYm": "2026-06"}},
    "rows": [{"tipo": "Series", "label": "Serie B"}],
}

# Simulates the real "mercado laboral" case: the group title has nothing to
# do with "desempleo", but one of its series is literally named that.
_BUNDLE_20 = {
    "context": {"id_grupo": 20, "nom_grupo": "Mercado Laboral"},
    "frecuencias": ["Mensual"],
    "unidades": {"Mensual": ["Porcentaje"]},
    "range": {"minYm": "2020-01", "maxYm": "2026-06"},
    "range_by_freq": {"Mensual": {"minYm": "2020-01", "maxYm": "2026-06"}},
    "rows": [
        {"tipo": "Cabeceras", "label": "NACIONAL"},
        {"tipo": "Series", "label": "Empleo Nacional"},
        {"tipo": "Series", "label": "Desempleo Nacional"},
    ],
}

_GRID_10 = {
    "columns": ["Ene 2026", "Feb 2026"],
    "rows": [
        {"tipo": "Cabeceras", "label": "TOTAL", "nivel": 1},
        {
            "tipo": "Series",
            "label": "Serie A",
            "ruta": "total\\serie a",
            "values": {"Ene 2026": 100.0, "Feb 2026": 110.0},
        },
    ],
}


def _mock_all_bundles(httpx_mock):
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/bundle/10",
        json=_BUNDLE_10,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/bundle/11",
        json=_BUNDLE_11,
    )
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/bundle/20",
        json=_BUNDLE_20,
    )


@pytest.fixture(autouse=True)
def _reset_cache():
    bce_client._tree_cache = TtlCache(ttl_seconds=60)
    bce_client._bundle_cache = TtlCache(ttl_seconds=60)
    bce_client._catalog_cache = TtlCache(ttl_seconds=60)
    yield


def test_index_tree_reconstructs_sections_and_subsections():
    indexed = bce_client._index_tree(_TREE)

    assert len(indexed) == 3
    assert indexed[0] == {
        "id_grupo": 10,
        "descripcion": "1.1.1  Grupo Uno",
        "seccion": "1.  SECCION A",
        "subseccion": "1.1  Subseccion A1",
    }
    # A nivel-2 node that is itself a leaf (id_grupo set) must not repeat
    # its own description as "subseccion".
    assert indexed[1] == {
        "id_grupo": 11,
        "descripcion": "1.2  Subseccion A2 (con grupo propio)",
        "seccion": "1.  SECCION A",
        "subseccion": "",
    }
    assert indexed[2]["seccion"] == "2.  SECCION B"


async def test_search_indicadores_matches_description_and_section(httpx_mock):
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/tree", json=_TREE
    )
    _mock_all_bundles(httpx_mock)

    by_desc = await bce_client.search_indicadores(query="grupo uno")
    assert by_desc["total"] == 1
    assert by_desc["indicadores"][0]["id_grupo"] == 10

    by_section = await bce_client.search_indicadores(query="seccion b")
    assert by_section["total"] == 1
    assert by_section["indicadores"][0]["id_grupo"] == 20


async def test_search_indicadores_matches_series_label_inside_a_group(httpx_mock):
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/tree", json=_TREE
    )
    _mock_all_bundles(httpx_mock)

    result = await bce_client.search_indicadores(query="desempleo")

    assert result["total"] == 1
    hit = result["indicadores"][0]
    assert hit["id_grupo"] == 20
    # The group title ("Mercado Laboral") never mentions "desempleo" --
    # this is exactly the case a group/section-only search would miss.
    assert "desempleo" not in hit["descripcion"].lower()
    assert hit["series_coincidentes"] == ["Desempleo Nacional"]
    # The raw per-group series list used for matching must not leak into
    # the returned entry.
    assert "series" not in hit


async def test_search_indicadores_omits_series_coincidentes_when_title_matched(
    httpx_mock,
):
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/tree", json=_TREE
    )
    _mock_all_bundles(httpx_mock)

    result = await bce_client.search_indicadores(query="mercado laboral")

    assert result["total"] == 1
    assert "series_coincidentes" not in result["indicadores"][0]


async def test_search_indicadores_uses_cache_across_calls(httpx_mock):
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/tree", json=_TREE
    )
    _mock_all_bundles(httpx_mock)

    await bce_client.search_indicadores(query="grupo")
    # A second call must not trigger another network request (httpx_mock
    # would fail the test on an unexpected/unmatched extra request) --
    # both the tree and every group's bundle must come from cache.
    await bce_client.search_indicadores(query="seccion")


async def test_get_indicador_uses_bundle_defaults(httpx_mock):
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/bundle/10",
        json=_BUNDLE_10,
    )
    httpx_mock.add_response(
        url=(
            "https://contenido.bce.fin.ec/wp-json/bcedata/v1/grid"
            "?id_grupo=10&frecuencia=Mensual&unidad=Millones+de+USD"
            "&desde=2020-01&hasta=2026-06"
        ),
        json=_GRID_10,
    )

    result = await bce_client.get_indicador(id_grupo=10)

    assert result["frecuencia"] == "Mensual"
    assert result["unidad"] == "Millones de USD"
    assert result["desde"] == "2020-01"
    assert result["hasta"] == "2026-06"
    assert result["periodos"] == ["Ene 2026", "Feb 2026"]
    assert len(result["series"]) == 1
    assert result["series"][0]["label"] == "Serie A"
    assert result["series"][0]["valores"]["Feb 2026"] == 110.0


async def test_get_indicador_respects_explicit_frecuencia_and_unidad(httpx_mock):
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/bundle/10",
        json=_BUNDLE_10,
    )
    httpx_mock.add_response(
        url=(
            "https://contenido.bce.fin.ec/wp-json/bcedata/v1/grid"
            "?id_grupo=10&frecuencia=Anual&unidad=Millones+de+USD"
            "&desde=2020&hasta=2025"
        ),
        json={"columns": ["2025"], "rows": []},
    )

    result = await bce_client.get_indicador(id_grupo=10, frecuencia="Anual")

    assert result["frecuencia"] == "Anual"
    assert result["desde"] == "2020"
    assert result["hasta"] == "2025"


async def test_get_indicador_falls_back_to_first_option_on_unknown_frecuencia(
    httpx_mock,
):
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/bundle/10",
        json=_BUNDLE_10,
    )
    httpx_mock.add_response(
        url=(
            "https://contenido.bce.fin.ec/wp-json/bcedata/v1/grid"
            "?id_grupo=10&frecuencia=Mensual&unidad=Millones+de+USD"
            "&desde=2020-01&hasta=2026-06"
        ),
        json=_GRID_10,
    )

    result = await bce_client.get_indicador(id_grupo=10, frecuencia="Semanal")

    assert result["frecuencia"] == "Mensual"


async def test_get_indicador_surfaces_api_error_message(httpx_mock):
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/bundle/999",
        status_code=404,
        json={"code": "bcedata_rest_bundle_not_found", "message": "Cuadro no encontrado"},
    )

    with pytest.raises(ValueError, match="Cuadro no encontrado"):
        await bce_client.get_indicador(id_grupo=999)


async def test_bundle_is_cached_across_lookups(httpx_mock):
    httpx_mock.add_response(
        url="https://contenido.bce.fin.ec/wp-json/bcedata/v1/bundle/10",
        json=_BUNDLE_10,
    )
    httpx_mock.add_response(
        url=(
            "https://contenido.bce.fin.ec/wp-json/bcedata/v1/grid"
            "?id_grupo=10&frecuencia=Mensual&unidad=Millones+de+USD"
            "&desde=2020-01&hasta=2026-06"
        ),
        json=_GRID_10,
    )
    httpx_mock.add_response(
        url=(
            "https://contenido.bce.fin.ec/wp-json/bcedata/v1/grid"
            "?id_grupo=10&frecuencia=Mensual&unidad=Millones+de+USD"
            "&desde=2020-01&hasta=2026-06"
        ),
        json=_GRID_10,
    )

    await bce_client.get_indicador(id_grupo=10)
    # Second call must reuse the cached bundle (only one bundle/10 response
    # was mocked) and only re-fetch the grid.
    await bce_client.get_indicador(id_grupo=10)

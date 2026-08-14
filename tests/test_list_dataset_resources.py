from tools.list_dataset_resources import _detect_periodic_series


def test_detect_periodic_series_finds_matching_group():
    resources = [
        {"name": "precios_semana_24.csv"},
        {"name": "precios_semana_25.csv"},
        {"name": "precios_semana_26.csv"},
        {"name": "diccionario_de_datos.pdf"},
    ]

    series = _detect_periodic_series(resources)

    assert series == [
        "precios_semana_24.csv",
        "precios_semana_25.csv",
        "precios_semana_26.csv",
    ]


def test_detect_periodic_series_requires_at_least_three():
    resources = [
        {"name": "precios_semana_24.csv"},
        {"name": "precios_semana_25.csv"},
        {"name": "diccionario_de_datos.pdf"},
    ]

    assert _detect_periodic_series(resources) == []


def test_detect_periodic_series_ignores_unrelated_names():
    resources = [
        {"name": "reporte_anual.csv"},
        {"name": "diccionario_de_datos.pdf"},
        {"name": "metadatos.json"},
    ]

    assert _detect_periodic_series(resources) == []

from tools.list_dataset_resources import detect_periodic_series


def test_detect_periodic_series_finds_matching_group():
    resources = [
        {"name": "precios_semana_24.csv"},
        {"name": "precios_semana_25.csv"},
        {"name": "precios_semana_26.csv"},
        {"name": "diccionario_de_datos.pdf"},
    ]

    series = detect_periodic_series(resources)

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

    assert detect_periodic_series(resources) == []


def test_detect_periodic_series_ignores_unrelated_names():
    resources = [
        {"name": "reporte_anual.csv"},
        {"name": "diccionario_de_datos.pdf"},
        {"name": "metadatos.json"},
    ]

    assert detect_periodic_series(resources) == []


def test_detect_periodic_series_groups_by_spanish_month_name():
    # Real case found live: MPCEIP's cacao price dataset names monthly
    # resources "..._2023_AGOSTO.csv", "..._2023_SEPTIEMBRE.csv", etc. --
    # same series, but differing by a month word, not a digit.
    resources = [
        {"name": "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_AGOSTO.csv"},
        {"name": "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_SEPTIEMBRE.csv"},
        {"name": "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_OCTUBRE.csv"},
        {"name": "diccionario_de_datos.pdf"},
    ]

    series = detect_periodic_series(resources)

    assert series == [
        "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_AGOSTO.csv",
        "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_SEPTIEMBRE.csv",
        "MPCEIP_PRECIO FOB_EXPORTACIONES CACAO_2023_OCTUBRE.csv",
    ]


def test_detect_periodic_series_does_not_match_month_substrings():
    # "enero" is a literal substring of "generosidad" (g-ENERO-sidad); the
    # \b word boundaries must stop it from being treated as a month token
    # there, or these three genuinely unrelated reports would wrongly group.
    resources = [
        {"name": "indice_generosidad_2021.csv"},
        {"name": "indice_generosidad_2022.csv"},
        {"name": "indice_generosidad_2023.csv"},
        {"name": "reporte_enero_2024.csv"},
    ]

    series = detect_periodic_series(resources)

    assert series == [
        "indice_generosidad_2021.csv",
        "indice_generosidad_2022.csv",
        "indice_generosidad_2023.csv",
    ]

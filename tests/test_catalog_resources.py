import json

from resources.catalog import _fuentes_payload


def test_fuentes_lists_every_integrated_source_family():
    payload = _fuentes_payload()
    sources = {source["id"]: source for source in payload["fuentes"]}

    assert {
        "ckan",
        "cuenca",
        "sri",
        "gobec",
        "sercop",
        "sgr",
        "igepn",
        "geo",
        "anda",
        "inec-estadisticas",
        "inec-biinec",
        "inec-censo",
        "bce",
        "sipa",
        "contraloria",
        "supercias",
        "supercias-financials",
        "superbancos",
        "cenace",
        "sut",
    } <= sources.keys()
    assert "search_biinec_extras" in sources["inec-biinec"]["tools"]
    assert "get_contraloria_informe" in sources["contraloria"]["tools"]
    assert "get_tramite_estadisticas" in sources["gobec"]["tools"]
    assert "search_informes_igepn" in sources["igepn"]["tools"]
    assert "get_sri_ruc_info" in sources["sri"]["tools"]
    assert "list_bce_indicadores_diarios" in sources["bce"]["tools"]
    assert "get_superbancos_seccion_archivos" in sources["superbancos"]["tools"]
    assert "get_cenace_tablero" in sources["cenace"]["tools"]
    assert "query_sut_indicador" in sources["sut"]["tools"]
    assert json.loads(json.dumps(payload, ensure_ascii=False))["fuentes"]

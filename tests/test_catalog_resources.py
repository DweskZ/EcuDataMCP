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
        "bce",
        "sipa",
        "contraloria",
        "supercias",
        "supercias-financials",
    } <= sources.keys()
    assert "search_biinec_extras" in sources["inec-biinec"]["tools"]
    assert "get_contraloria_informe" in sources["contraloria"]["tools"]
    assert json.loads(json.dumps(payload, ensure_ascii=False))["fuentes"]

from helpers.biinec_extras import list_extras, search_extras


def test_list_extras_has_entries():
    items = list_extras()
    assert len(items) >= 3
    for item in items:
        assert item["nombre"]
        assert item["descripcion"]
        assert item["verificado"]


def test_search_extras_empty_query_returns_all():
    assert search_extras() == list_extras()


def test_search_extras_matches_name_accent_insensitive():
    matches = search_extras("desechos peligrosos")
    assert len(matches) == 1
    assert "Desechos Peligrosos" in matches[0]["nombre"]


def test_search_extras_matches_description():
    matches = search_extras("enemdu")
    assert any("ENEMDU" in m["nombre"] for m in matches)


def test_search_extras_no_match():
    assert search_extras("empleo formal sector privado") == []

from helpers.acronyms import expand_acronyms


def test_expands_known_acronym():
    result = expand_acronyms("ENEMDU")
    assert result.startswith("ENEMDU ")
    assert "encuesta nacional de empleo" in result.lower()


def test_expands_case_insensitively():
    result = expand_acronyms("ruc provincia")
    assert "registro unico de contribuyentes" in result.lower()


def test_leaves_unknown_query_unchanged():
    assert expand_acronyms("cacao exportaciones") == "cacao exportaciones"


def test_does_not_duplicate_expansion_already_in_query():
    query = "registro unico de contribuyentes ruc"
    assert expand_acronyms(query) == query


def test_expands_multiple_acronyms_once_each():
    result = expand_acronyms("ruc ruc iess")
    assert result.lower().count("registro unico de contribuyentes") == 1
    assert result.lower().count("instituto ecuatoriano de seguridad social") == 1


def test_empty_query_returns_unchanged():
    assert expand_acronyms("") == ""


def test_wildcard_query_returns_unchanged():
    assert expand_acronyms("*:*") == "*:*"

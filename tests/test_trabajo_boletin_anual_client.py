import pytest

from helpers import trabajo_boletin_anual_client

# This client is a small, hand-verified hardcoded set (see the module
# docstring for why: the only page that ever listed multiple editions can't
# be scraped live). No HTTP calls are made, so no pytest-httpx mocking is
# needed here -- plain unit tests against the module's public function.


@pytest.mark.asyncio
async def test_search_boletines_lists_all_known_editions():
    result = await trabajo_boletin_anual_client.search_boletines()

    assert result["total"] == 3
    assert result["total_conocido"] == 3
    assert result["cobertura_incompleta"] is True
    anios = {e["anio"] for e in result["ediciones"]}
    assert anios == {"2020", "2021", "2022"}


@pytest.mark.asyncio
async def test_search_boletines_every_edition_has_a_direct_pdf_url():
    result = await trabajo_boletin_anual_client.search_boletines()

    for edicion in result["ediciones"]:
        assert edicion["url"].startswith(
            "https://www.trabajo.gob.ec/wp-content/uploads/"
        )
        assert edicion["url"].endswith(".pdf")
        assert edicion["formato"] == "PDF"


@pytest.mark.asyncio
async def test_search_boletines_filters_by_year_query():
    result = await trabajo_boletin_anual_client.search_boletines(query="2021")

    assert result["total"] == 1
    assert result["total_conocido"] == 3
    assert result["ediciones"][0]["anio"] == "2021"
    assert "BoletinAnual_2021_compressed" in result["ediciones"][0]["url"]


@pytest.mark.asyncio
async def test_search_boletines_filters_accent_insensitively_on_title():
    result = await trabajo_boletin_anual_client.search_boletines(query="MERCADO LABORAL")

    # All three editions share "Mercado Laboral" in their title.
    assert result["total"] == 3


@pytest.mark.asyncio
async def test_search_boletines_query_with_no_match_returns_empty():
    result = await trabajo_boletin_anual_client.search_boletines(query="2019")

    assert result["total"] == 0
    assert result["total_conocido"] == 3
    assert result["ediciones"] == []


@pytest.mark.asyncio
async def test_search_boletines_only_2022_marked_as_currently_linked():
    result = await trabajo_boletin_anual_client.search_boletines()

    linked = {e["anio"] for e in result["ediciones"] if e["enlazado_en_pagina_indice"]}
    assert linked == {"2022"}

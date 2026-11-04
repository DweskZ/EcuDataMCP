import re

import httpx
import pytest

from helpers import msp_gacetas_client as client

_WP_URL = re.compile(rf"^{re.escape(client._WP_API_URL)}\?.*search=gaceta")

# Slugs as the live search returned them on 2026-11-04: several families per
# series, an unrelated news post, and an empty landing page that matches no
# series.
_POSTS = [
    {"slug": "gacetas-vectoriales-2026", "link": "https://www.salud.gob.ec/gacetas-vectoriales-2026/"},
    {"slug": "gaceta-etas-se-2022", "link": "https://www.salud.gob.ec/gaceta-etas-se-2022/"},
    {"slug": "brotes", "link": "https://www.salud.gob.ec/brotes/"},
    {
        "slug": "gacetas-inmunoprevenibles-2025",
        "link": "https://www.salud.gob.ec/gacetas-inmunoprevenibles-2025/",
    },
    {"slug": "gacetas-epidemiologicas-2", "link": "https://www.salud.gob.ec/gacetas-epidemiologicas-2/"},
    {"slug": "ministerio-presenta-gaceta", "link": "https://www.salud.gob.ec/ministerio-presenta-gaceta/"},
]

_VECTORIALES = """
<table>
<tr><td><a href="https://www.salud.gob.ec/wp-content/uploads/2026/10/ETV_Gaceta_42.pdf">42</a></td></tr>
<tr><td><a href="https://www.salud.gob.ec/wp-content/uploads/2026/10/ETV_Gaceta_42.pdf">42</a></td></tr>
<tr><td><a href="https://www.salud.gob.ec/wp-content/uploads/2025/06/Eventos-FA-SE-24.pdf">FA</a></td></tr>
<tr><td><a href="//www.salud.gob.ec/wp-content/uploads/downloads/2019/03/VECTORES-10_20.pdf">10</a></td></tr>
<tr><td><a href="http://instituciones.msp.gob.ec/images/gaceta1.pdf">2012</a></td></tr>
</table>
"""
_ETAS = '<a href="https://www.salud.gob.ec/wp-content/uploads/2022/12/ETAS-52.pdf">52</a>'
_BROTES = (
    '<a href="https://www.salud.gob.ec/wp-content/uploads/2022/10/5.-Gaceta-brotes_SE-34.pdf">x</a>'
)
_INMUNO = (
    '<a href="https://www.salud.gob.ec/wp-content/uploads/2025/12/'
    'Eventos-tosferina-CT_-DNVE-SE-48.pdf">x</a>'
)


@pytest.fixture(autouse=True)
def clear_cache():
    client._paginas_cache.clear()
    client._pagina_cache.clear()
    yield
    client._paginas_cache.clear()
    client._pagina_cache.clear()


@pytest.mark.parametrize(
    ("stem", "semana", "desde"),
    [
        ("Gaceta-EPV-SE-35", 35, None),
        ("Gaceta-EPV-SE-22-1", 22, None),
        ("indicadores-SIVE_2025-SE-01-53", 53, 1),
        ("BOLETIN-IRAG-ANO-2025-SE-01-SE45", 45, 1),
        ("Lepra-SE-01-03", 3, 1),
        ("5.-Gaceta-brotes-41", 41, None),
        ("ETV_Gaceta_42", 42, None),
        ("VECTORES-10_20", 10, None),
        ("INMUNO_03_2020", 3, None),
        ("gaceta_brotesSE31", 31, None),
        ("gaceta_epidemiologica_s30", 30, None),
        ("Eventos-INMUNOPREVENIBLES-DNVE-SE-341", 34, None),
        ("INMUNOPREVENIBLES-SE-81", 8, None),
        ("SEMANA-47", 47, None),
        ("Gaceta N35", 35, None),
        ("Gaceta-N36", 36, None),
        ("Neumonia", None, None),
        ("Gaceta-MNN-I-trimestre-2026", None, None),
        ("CIERRE-PROCESO-MM-2018", None, None),
    ],
)
def test_semana_handles_every_naming_convention(stem, semana, desde):
    assert client._semana(stem) == (semana, desde)


def test_slugs_map_to_series():
    assert client._serie_de_slug("gacetas-enfermedades-transmitidas-por-agua-o-alimentos-2019") == "etas"
    assert client._serie_de_slug("gacetas-epidemiologicas-2023") == "irag"
    assert client._serie_de_slug("informacion-de-enfermedades-de-la-piel-reemergentes") == (
        "piel_reemergentes"
    )
    assert client._serie_de_slug("gacetas-de-muerte-materna-2017") == "muerte_materna"
    assert client._serie_de_slug("gacetas-epidemiologicas-2") is None
    assert client._serie_de_slug("brotes-2023") == "brotes"


def test_series_candidatas_narrow_only_on_series_words():
    assert client._series_candidatas(["vectoriales", "2026"]) == {"vectoriales"}
    assert client._series_candidatas(["dengue"]) == {"vectoriales"}
    assert client._series_candidatas(["2026"]) == set(client._SERIES_BY_KEY)


async def test_search_gacetas_parses_classifies_and_dedups(httpx_mock):
    httpx_mock.add_response(url=_WP_URL, json=_POSTS, headers={"X-WP-TotalPages": "1"})
    httpx_mock.add_response(url="https://www.salud.gob.ec/gacetas-vectoriales-2026/", text=_VECTORIALES)
    httpx_mock.add_response(url="https://www.salud.gob.ec/gaceta-etas-se-2022/", text=_ETAS)
    httpx_mock.add_response(url="https://www.salud.gob.ec/brotes/", text=_BROTES)
    httpx_mock.add_response(
        url="https://www.salud.gob.ec/gacetas-inmunoprevenibles-2025/", text=_INMUNO
    )

    result = await client.search_gacetas()

    assert result["por_serie"] == {"brotes": 1, "etas": 1, "inmunoprevenibles": 1, "vectoriales": 3}
    assert result["paginas_con_error"] == []
    vect = [a for a in result["archivos"] if a["serie"] == "vectoriales"]
    old = next(a for a in vect if a["titulo"] == "VECTORES-10_20")
    assert old["url"].startswith("https://www.salud.gob.ec/wp-content/uploads/downloads/2019/")
    assert (old["anio"], old["mes"], old["semana"]) == ("2019", "03", "10")
    assert next(a for a in vect if "FA" in a["titulo"])["tipo"] == "fiebre_amarilla"
    assert not any("instituciones.msp" in a["url"] for a in result["archivos"])
    inmuno = next(a for a in result["archivos"] if a["serie"] == "inmunoprevenibles")
    assert (inmuno["tipo"], inmuno["semana"]) == ("tosferina", "48")


async def test_search_gacetas_fetches_only_the_named_series(httpx_mock):
    httpx_mock.add_response(url=_WP_URL, json=_POSTS, headers={"X-WP-TotalPages": "1"})
    httpx_mock.add_response(url="https://www.salud.gob.ec/gaceta-etas-se-2022/", text=_ETAS)

    result = await client.search_gacetas("etas 52")

    assert [a["titulo"] for a in result["archivos"]] == ["ETAS-52"]


async def test_failed_page_is_reported_not_fatal(httpx_mock, monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr(client.asyncio, "sleep", no_sleep)
    httpx_mock.add_response(url=_WP_URL, json=_POSTS, headers={"X-WP-TotalPages": "1"})
    httpx_mock.add_response(url="https://www.salud.gob.ec/gacetas-vectoriales-2026/", text=_VECTORIALES)
    httpx_mock.add_response(url="https://www.salud.gob.ec/gaceta-etas-se-2022/", text=_ETAS)
    httpx_mock.add_response(
        url="https://www.salud.gob.ec/gacetas-inmunoprevenibles-2025/", text=_INMUNO
    )
    httpx_mock.add_response(url="https://www.salud.gob.ec/brotes/", status_code=503, is_reusable=True)

    result = await client.search_gacetas()

    assert result["paginas_con_error"] == ["https://www.salud.gob.ec/brotes/"]
    assert "incompleta" in result["nota"]


async def test_wp_api_is_paged(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(rf"^{re.escape(client._WP_API_URL)}\?.*page=1&"),
        json=_POSTS[:1],
        headers={"X-WP-TotalPages": "2"},
    )
    httpx_mock.add_response(
        url=re.compile(rf"^{re.escape(client._WP_API_URL)}\?.*page=2&"),
        json=_POSTS[1:2],
        headers={"X-WP-TotalPages": "2"},
    )

    paginas = await client._fetch_paginas()

    assert [p["serie"] for p in paginas] == ["vectoriales", "etas"]


def test_unknown_host_is_not_salud():
    assert not client._is_salud_url(str(httpx.URL("https://salud.gob.ec.evil.com/x.pdf")))


async def test_unreachable_site_names_the_host(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectTimeout(""), url=_WP_URL)

    with pytest.raises(ValueError, match=r"salud.gob.ec no respondió \(ConnectTimeout\)"):
        await client.search_gacetas("vih")

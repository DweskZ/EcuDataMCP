import httpx
import pytest

from helpers import msp_gacetas_inmunoprevenibles_client as client

# Trimmed but structurally faithful excerpt of the real WordPress REST API
# response (salud.gob.ec/wp-json/wp/v2/posts?search=inmunoprevenibles,
# confirmed live 2026-09-10): mixes real archive-page slugs (prefixed
# "gacetas-inmunoprevenibles") with unrelated news articles that also
# matched the search term, plus one empty landing-page slug that is a real
# archive-prefixed slug but has no PDF links at all.
_WP_POSTS_JSON = [
    {
        "slug": "gobierno-de-daniel-noboa-destina-usd-165-mil-en-vacunas",
        "link": "https://www.salud.gob.ec/gobierno-de-daniel-noboa-destina-usd-165-mil-en-vacunas/",
    },
    {
        "slug": "gacetas-inmunoprevenibles-2026",
        "link": "https://www.salud.gob.ec/gacetas-inmunoprevenibles-2026/",
    },
    {
        "slug": "gacetas-inmunoprevenibles-2025",
        "link": "https://www.salud.gob.ec/gacetas-inmunoprevenibles-2025/",
    },
    {
        "slug": "gacetas-inmunoprevenibles-2",
        "link": "https://www.salud.gob.ec/gacetas-inmunoprevenibles-2/",
    },
    {
        "slug": "enfermedades-prevenibles-por-vacunacion-2023",
        "link": "https://www.salud.gob.ec/enfermedades-prevenibles-por-vacunacion-2023/",
    },
]

_PAGE_2026_HTML = """
<html><body>
<figure class="wp-block-table"><table><tbody>
<tr><td><a href="https://www.salud.gob.ec/wp-content/uploads/2026/09/Gaceta-EPV-SE-35.pdf">SE 35</a></td></tr>
<tr><td><a href="https://www.salud.gob.ec/wp-content/uploads/2026/08/Gaceta-EPV-SE-34.pdf">SE 34</a></td></tr>
</tbody></table></figure>
</body></html>
"""

_PAGE_2025_HTML = """
<html><body>
<figure class="wp-block-table"><table><tbody>
<tr><td><a href="https://www.salud.gob.ec/wp-content/uploads/2025/12/Eventos-Inmunoprevenibles-CT_-DNVE-SE-48.pdf">General</a></td></tr>
<tr><td><a href="https://www.salud.gob.ec/wp-content/uploads/2025/12/Eventos-tosferina-CT_-DNVE-SE-48.pdf">Tosferina</a></td></tr>
</tbody></table></figure>
</body></html>
"""

_PAGE_2_HTML = "<html><body><p>Página informativa sin archivos.</p></body></html>"

_EMPTY_WP_POSTS_JSON: list = []


@pytest.fixture(autouse=True)
def clear_cache():
    client._paginas_cache.clear()
    client._archivos_cache.clear()
    yield
    client._paginas_cache.clear()
    client._archivos_cache.clear()


async def test_fetch_paginas_filters_to_archive_prefixed_slugs_only(httpx_mock):
    httpx_mock.add_response(url=httpx.URL(client._WP_API_URL, params={
        "search": "inmunoprevenibles", "per_page": 100, "_fields": "slug,link",
    }), json=_WP_POSTS_JSON)

    paginas = await client._fetch_paginas()

    assert paginas == [
        "https://www.salud.gob.ec/gacetas-inmunoprevenibles-2026/",
        "https://www.salud.gob.ec/gacetas-inmunoprevenibles-2025/",
        "https://www.salud.gob.ec/gacetas-inmunoprevenibles-2/",
    ]
    # Unrelated news article and the non-archive-prefixed slug are excluded.
    assert not any("gobierno-de-daniel-noboa" in p for p in paginas)
    assert not any("enfermedades-prevenibles" in p for p in paginas)


async def test_search_gacetas_aggregates_and_dedupes_across_pages(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(client._WP_API_URL, params={
            "search": "inmunoprevenibles", "per_page": 100, "_fields": "slug,link",
        }),
        json=_WP_POSTS_JSON,
    )
    httpx_mock.add_response(url=client._BASE + "/gacetas-inmunoprevenibles-2026/", html=_PAGE_2026_HTML)
    httpx_mock.add_response(url=client._BASE + "/gacetas-inmunoprevenibles-2025/", html=_PAGE_2025_HTML)
    httpx_mock.add_response(url=client._BASE + "/gacetas-inmunoprevenibles-2/", html=_PAGE_2_HTML)

    result = await client.search_gacetas_inmunoprevenibles()

    # 2 from 2026 + 2 from 2025 + 0 from the empty landing page.
    assert result["total_en_archivo"] == 4
    assert result["total"] == 4


async def test_search_gacetas_extracts_semana_anio_mes_and_tipo(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(client._WP_API_URL, params={
            "search": "inmunoprevenibles", "per_page": 100, "_fields": "slug,link",
        }),
        json=_WP_POSTS_JSON,
    )
    httpx_mock.add_response(url=client._BASE + "/gacetas-inmunoprevenibles-2026/", html=_PAGE_2026_HTML)
    httpx_mock.add_response(url=client._BASE + "/gacetas-inmunoprevenibles-2025/", html=_PAGE_2025_HTML)
    httpx_mock.add_response(url=client._BASE + "/gacetas-inmunoprevenibles-2/", html=_PAGE_2_HTML)

    result = await client.search_gacetas_inmunoprevenibles()

    by_titulo = {a["titulo"]: a for a in result["archivos"]}
    gaceta_35 = by_titulo["Gaceta-EPV-SE-35"]
    assert gaceta_35["anio"] == "2026"
    assert gaceta_35["mes"] == "09"
    assert gaceta_35["semana"] == "35"
    assert gaceta_35["tipo"] == "general"

    tosferina = by_titulo["Eventos-tosferina-CT_-DNVE-SE-48"]
    assert tosferina["tipo"] == "tosferina"
    assert tosferina["semana"] == "48"


async def test_search_gacetas_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(client._WP_API_URL, params={
            "search": "inmunoprevenibles", "per_page": 100, "_fields": "slug,link",
        }),
        json=_WP_POSTS_JSON,
    )
    httpx_mock.add_response(url=client._BASE + "/gacetas-inmunoprevenibles-2026/", html=_PAGE_2026_HTML)
    httpx_mock.add_response(url=client._BASE + "/gacetas-inmunoprevenibles-2025/", html=_PAGE_2025_HTML)
    httpx_mock.add_response(url=client._BASE + "/gacetas-inmunoprevenibles-2/", html=_PAGE_2_HTML)

    result = await client.search_gacetas_inmunoprevenibles(query="tosferina")

    assert result["total"] == 1
    assert result["archivos"][0]["tipo"] == "tosferina"


async def test_empty_page_list_is_not_cached(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(client._WP_API_URL, params={
            "search": "inmunoprevenibles", "per_page": 100, "_fields": "slug,link",
        }),
        json=_EMPTY_WP_POSTS_JSON,
    )
    httpx_mock.add_response(
        url=httpx.URL(client._WP_API_URL, params={
            "search": "inmunoprevenibles", "per_page": 100, "_fields": "slug,link",
        }),
        json=_WP_POSTS_JSON,
    )

    first = await client._fetch_paginas()
    assert first == []

    second = await client._fetch_paginas()
    assert len(second) == 3

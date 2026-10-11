import pytest

from helpers import inec_client

_SEED_URLS = inec_client._SEED_PAGE_URLS
_IPC_SEED, _ENEMDU_SEED = _SEED_URLS

_MENU_HTML = """
<html><body>
<ul>
<li><a class="mega-menu-link" href="https://www.ecuadorencifras.gob.ec/indice-de-precios-al-consumidor/">Índice de Precios al Consumidor</a></li>
<li><a class="mega-menu-link" href="https://www.ecuadorencifras.gob.ec/pobreza2/">Pobreza</a></li>
<li><a class="mega-menu-link" href="https://www.ecuadorencifras.gob.ec/indice-de-precios-al-consumidor/">Índice de Precios al Consumidor</a></li>
</ul>
</body></html>
"""

# Mirrors the real page shape: a top-level mega-menu-link plus dropdown
# children that use a different <li class="menu-item ..."> + plain <a> shape
# -- the pattern that hid enemdu-anual/enemdu-trimestral from the original
# single-regex scraper (see RESEARCH.md § Novena pasada).
_ENEMDU_MENU_HTML = """
<html><body>
<ul>
<li><a class="mega-menu-link" href="https://www.ecuadorencifras.gob.ec/estadisticas-laborales-enemdu/">Empleo</a></li>
<li id="menu-item-1" class="menu-item menu-item-type-post_type"><a href="https://www.ecuadorencifras.gob.ec/enemdu-anual/">ENEMDU Anual <img src="x.gif"/></a></li>
<li id="menu-item-2" class="menu-item menu-item-type-custom"><a title="https://old" href="https://www.ecuadorencifras.gob.ec/enemdu-trimestral/">ENEMDU Trimestral <img src="x.gif"/></a></li>
</ul>
</body></html>
"""

_TOPIC_HTML = """
<html><head><title>Índice de Precios al Consumidor &#8211; IPC | </title></head>
<body>
<a href="https://www.ecuadorencifras.gob.ec/documentos/web-inec/Boletin_Tecnico_2026.pdf" target="_blank"><img/></a>
<a href="https://www.ecuadorencifras.gob.ec/documentos/web-inec/Tabulados_y_series_historicas_CSV.zip"><img/></a>
<a href="https://www.gobiernoelectronico.gob.ec/wp-content/uploads/2019/Acuerdo-012-2019.pdf">Acuerdo</a>
</body></html>
"""

_API_BASE = inec_client._API_BASE


@pytest.fixture(autouse=True)
def clear_caches():
    inec_client._topics_cache.clear()
    inec_client._topic_files_cache.clear()
    inec_client._categories_cache.clear()
    inec_client._publicacion_files_cache.clear()
    yield
    inec_client._topics_cache.clear()
    inec_client._topic_files_cache.clear()
    inec_client._categories_cache.clear()
    inec_client._publicacion_files_cache.clear()


# -- topic-page layer (search_topics / get_topic_files) ----------------------


@pytest.mark.asyncio
async def test_search_topics(httpx_mock):
    httpx_mock.add_response(url=_IPC_SEED, html=_MENU_HTML)
    httpx_mock.add_response(url=_ENEMDU_SEED, html=_ENEMDU_MENU_HTML)

    result = await inec_client.search_topics(query="precios")

    assert result["total"] == 1
    assert result["temas"][0]["nombre"] == "Índice de Precios al Consumidor"
    assert result["temas"][0]["url"] == (
        "https://www.ecuadorencifras.gob.ec/indice-de-precios-al-consumidor/"
    )


@pytest.mark.asyncio
async def test_search_topics_includes_curated_extra_topics(httpx_mock):
    httpx_mock.add_response(url=_IPC_SEED, html=_MENU_HTML)
    httpx_mock.add_response(url=_ENEMDU_SEED, html=_ENEMDU_MENU_HTML)

    result = await inec_client.search_topics(query="clasificador")

    assert len(result["temas"]) == 1
    assert result["temas"][0]["url"] == inec_client._EXTRA_TOPICS[0]["url"]


@pytest.mark.asyncio
async def test_search_topics_merges_both_seed_pages(httpx_mock):
    httpx_mock.add_response(url=_IPC_SEED, html=_MENU_HTML)
    httpx_mock.add_response(url=_ENEMDU_SEED, html=_ENEMDU_MENU_HTML)

    result = await inec_client.search_topics()

    urls = {t["url"] for t in result["temas"]}
    # From the IPC seed's top-level menu.
    assert "https://www.ecuadorencifras.gob.ec/pobreza2/" in urls
    # From the ENEMDU seed's dropdown children -- missed by the old
    # single-seed, single-regex scraper.
    assert "https://www.ecuadorencifras.gob.ec/enemdu-anual/" in urls
    assert "https://www.ecuadorencifras.gob.ec/enemdu-trimestral/" in urls


@pytest.mark.asyncio
async def test_search_topics_dedupes_repeated_menu_entries(httpx_mock):
    httpx_mock.add_response(url=_IPC_SEED, html=_MENU_HTML)
    httpx_mock.add_response(url=_ENEMDU_SEED, html=_ENEMDU_MENU_HTML)

    topics = await inec_client._fetch_topics()

    urls = [t["url"] for t in topics]
    assert len(urls) == len(set(urls))


@pytest.mark.asyncio
async def test_fetch_topics_tolerates_one_seed_failing(httpx_mock):
    httpx_mock.add_response(url=_IPC_SEED, html=_MENU_HTML)
    httpx_mock.add_response(url=_ENEMDU_SEED, status_code=500, content=b"boom")

    topics = await inec_client._fetch_topics()

    # The working seed's topics still come through.
    assert any(t["url"].endswith("pobreza2/") for t in topics)


@pytest.mark.asyncio
async def test_fetch_topics_raises_when_every_seed_fails(httpx_mock):
    httpx_mock.add_response(url=_IPC_SEED, status_code=500, content=b"boom")
    httpx_mock.add_response(url=_ENEMDU_SEED, status_code=500, content=b"boom")

    with pytest.raises(ValueError, match="No se pudo cargar"):
        await inec_client._fetch_topics()


@pytest.mark.asyncio
async def test_get_topic_files(httpx_mock):
    topic_url = "https://www.ecuadorencifras.gob.ec/indice-de-precios-al-consumidor/"
    httpx_mock.add_response(url=topic_url, html=_TOPIC_HTML)

    result = await inec_client.get_topic_files(topic_url)

    assert result["titulo"] == "Índice de Precios al Consumidor – IPC"
    urls = [f["url"] for f in result["archivos"]]
    assert (
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/Boletin_Tecnico_2026.pdf"
        in urls
    )
    assert (
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/"
        "Tabulados_y_series_historicas_CSV.zip" in urls
    )
    # Files hosted off ecuadorencifras.gob.ec/documentos/ are not picked up.
    assert not any("gobiernoelectronico" in u for u in urls)

    formats = {f["url"]: f["format"] for f in result["archivos"]}
    assert (
        formats[
            "https://www.ecuadorencifras.gob.ec/documentos/web-inec/Boletin_Tecnico_2026.pdf"
        ]
        == "PDF"
    )


@pytest.mark.asyncio
async def test_get_topic_files_tolerates_doubled_slash_in_file_links(httpx_mock):
    # Confirmed live on the Geografia_Estadistica micrositio: real links
    # look like "ecuadorencifras.gob.ec//documentos/..." (doubled slash) --
    # a literal single "/" in the regex missed these entirely (19 files
    # found instead of the real 115 on that page).
    topic_url = "https://www.ecuadorencifras.gob.ec/geoportal/"
    html = (
        '<html><body><a href="https://www.ecuadorencifras.gob.ec//documentos/'
        'web-inec/Cartografia/Clasificador_Geografico/2001/SHP.zip">2001</a>'
        "</body></html>"
    )
    httpx_mock.add_response(url=topic_url, html=html)

    result = await inec_client.get_topic_files(topic_url)

    assert len(result["archivos"]) == 1
    assert result["archivos"][0]["url"].endswith("2001/SHP.zip")


@pytest.mark.asyncio
async def test_get_topic_files_follows_related_landing_pages(httpx_mock):
    # Issue #55: the ENDI topic page lists no files itself; its image buttons
    # link to per-round landing pages (one with underscores in the slug) that
    # hold the downloads. Menu links to other surveys must not be followed.
    base = "https://www.ecuadorencifras.gob.ec/"
    topic_url = base + "encuesta-nacional-sobre-desnutricion-infantil/"
    round_url = base + "encuesta_nacional_desnutricion_infantil/"
    topic_html = (
        "<html><body>"
        '<li class="menu-item"><a href="' + base + 'trabajo-infantil/">Trabajo</a></li>'
        '<a href="' + base + 'encuesta-nacional-multiproposito-de-hogares/">ENEMDU</a>'
        '<a href="' + base + 'wp-content/uploads/2024/09/Banner_ENDI_1.jpg"></a>'
        '<a href="' + round_url + '"></a>'
        "</body></html>"
    )
    round_html = (
        '<html><body><a href="' + base + "documentos/web-inec/ENDI/R2/"
        'BDD_ENDI_R2_dta.zip">Base DTA</a></body></html>'
    )
    httpx_mock.add_response(url=topic_url, html=topic_html)
    httpx_mock.add_response(url=round_url, html=round_html)

    result = await inec_client.get_topic_files(topic_url)

    assert [f["url"].rsplit("/", 1)[-1] for f in result["archivos"]] == [
        "BDD_ENDI_R2_dta.zip"
    ]
    assert result["paginas_relacionadas"] == [round_url]


_BASE = "https://www.ecuadorencifras.gob.ec/"
_HUB_URL = _BASE + "encuesta-nacional-sobre-desnutricion-infantil/"


def _file_page(name: str) -> str:
    return f'<html><body><a href="{_BASE}documentos/web-inec/ENDI/{name}">x</a></body></html>'


def _hub_page(*slugs: str) -> str:
    links = "".join(f'<a href="{_BASE}{s}/"></a>' for s in slugs)
    return f"<html><body>{links}</body></html>"


@pytest.mark.asyncio
async def test_get_topic_files_related_pages_year_filter(httpx_mock):
    r1 = _BASE + "endi_desnutricion_infantil_2023/"
    r2 = _BASE + "endi_desnutricion_infantil_2024/"
    httpx_mock.add_response(
        url=_HUB_URL, html=_hub_page(r1.split("/")[-2], r2.split("/")[-2])
    )
    httpx_mock.add_response(url=r1, html=_file_page("BDD_2023.zip"))
    httpx_mock.add_response(url=r2, html=_file_page("BDD_2024.zip"))

    result = await inec_client.get_topic_files(_HUB_URL, year=2024)

    assert [f["url"].rsplit("/", 1)[-1] for f in result["archivos"]] == ["BDD_2024.zip"]


@pytest.mark.asyncio
async def test_get_topic_files_related_page_failure_is_skipped(httpx_mock):
    ok = _BASE + "endi_desnutricion_ok/"
    bad = _BASE + "endi_desnutricion_bad/"
    httpx_mock.add_response(
        url=_HUB_URL, html=_hub_page("endi_desnutricion_ok", "endi_desnutricion_bad")
    )
    httpx_mock.add_response(url=ok, html=_file_page("OK.zip"))
    httpx_mock.add_response(url=bad, status_code=500, content=b"boom")

    result = await inec_client.get_topic_files(_HUB_URL)

    assert [f["url"].rsplit("/", 1)[-1] for f in result["archivos"]] == ["OK.zip"]
    assert result["paginas_relacionadas"] == [ok]


@pytest.mark.asyncio
async def test_get_topic_files_related_pages_are_capped(httpx_mock):
    slugs = [f"endi_desnutricion_r{i}" for i in range(5)]
    httpx_mock.add_response(url=_HUB_URL, html=_hub_page(*slugs))
    for s in slugs[:3]:
        httpx_mock.add_response(url=_BASE + s + "/", html=_file_page(f"{s}.zip"))

    result = await inec_client.get_topic_files(_HUB_URL)

    assert len(result["archivos"]) == 3


@pytest.mark.asyncio
async def test_get_topic_files_with_own_files_skips_related_pages(httpx_mock):
    html = _file_page("OWN.zip").replace(
        "</body>", f'<a href="{_BASE}endi_desnutricion_r1/"></a></body>'
    )
    httpx_mock.add_response(url=_HUB_URL, html=html)

    result = await inec_client.get_topic_files(_HUB_URL)

    assert "paginas_relacionadas" not in result
    assert len(result["archivos"]) == 1


@pytest.mark.asyncio
async def test_get_topic_files_rejects_foreign_url():
    with pytest.raises(ValueError, match="fuera de ecuadorencifras"):
        await inec_client.get_topic_files("https://example.com/foo/")


# -- WordPress REST API layer (search_publicaciones / get_publicacion_files) -

_CATEGORIES_PAGE_1 = [{"id": i, "name": f"Categoría {i}"} for i in range(1, 101)]
_CATEGORIES_PAGE_2 = [{"id": 200, "name": "Economía Laboral"}]


def _mock_categories(httpx_mock):
    httpx_mock.add_response(
        url=f"{_API_BASE}/categories?per_page=100&page=1",
        json=_CATEGORIES_PAGE_1,
    )
    httpx_mock.add_response(
        url=f"{_API_BASE}/categories?per_page=100&page=2",
        json=_CATEGORIES_PAGE_2,
    )


@pytest.mark.asyncio
async def test_fetch_categories_paginates_until_a_short_page(httpx_mock):
    _mock_categories(httpx_mock)

    categories = await inec_client._fetch_categories()

    assert len(categories) == 101
    assert categories[200] == "Economía Laboral"


@pytest.mark.asyncio
async def test_search_publicaciones_reports_total_and_resolves_categories(httpx_mock):
    _mock_categories(httpx_mock)
    httpx_mock.add_response(
        url=(
            f"{_API_BASE}/posts?per_page=5&offset=0&orderby=date&order=desc"
            "&_fields=id%2Clink%2Cdate%2Cmodified%2Ctitle%2Ccategories&search=enemdu"
        ),
        json=[
            {
                "id": 39131,
                "link": "https://www.ecuadorencifras.gob.ec/empleo-mayo-2026/",
                "date": "2026-06-22T10:00:00",
                "modified": "2026-06-22T10:00:00",
                "title": {"rendered": "Empleo Mayo 2026"},
                "categories": [200],
            }
        ],
        headers={"X-WP-Total": "17"},
    )

    result = await inec_client.search_publicaciones(query="enemdu", limit=5)

    assert result["total"] == 17
    assert result["offset"] == 0
    post = result["publicaciones"][0]
    assert post["id"] == 39131
    assert post["titulo"] == "Empleo Mayo 2026"
    assert post["fecha_publicacion"] == "2026-06-22"
    assert post["categorias"] == ["Economía Laboral"]


@pytest.mark.asyncio
async def test_search_publicaciones_clamps_limit_and_offset(httpx_mock):
    _mock_categories(httpx_mock)
    httpx_mock.add_response(
        url=(
            f"{_API_BASE}/posts?per_page=100&offset=0&orderby=date&order=desc"
            "&_fields=id%2Clink%2Cdate%2Cmodified%2Ctitle%2Ccategories"
        ),
        json=[],
        headers={"X-WP-Total": "0"},
    )

    result = await inec_client.search_publicaciones(limit=500, offset=-5)

    assert result["offset"] == 0
    assert result["publicaciones"] == []


@pytest.mark.asyncio
async def test_get_publicacion_files_by_id(httpx_mock):
    _mock_categories(httpx_mock)
    httpx_mock.add_response(
        url=f"{_API_BASE}/posts?include=39131",
        json=[
            {
                "id": 39131,
                "link": "https://www.ecuadorencifras.gob.ec/empleo-mayo-2026/",
                "date": "2026-06-22T10:00:00",
                "modified": "2026-06-22T10:00:00",
                "title": {"rendered": "Empleo Mayo 2026"},
                "categories": [200],
                "content": {
                    "rendered": (
                        '<a href="https://www.ecuadorencifras.gob.ec/documentos/web-inec/'
                        'EMPLEO/2026/Mayo_2026/202605_MercadoLaboral.pdf">boletín</a>'
                    )
                },
            }
        ],
    )

    result = await inec_client.get_publicacion_files(39131)

    assert result["titulo"] == "Empleo Mayo 2026"
    assert len(result["archivos"]) == 1
    assert result["archivos"][0]["format"] == "PDF"


@pytest.mark.asyncio
async def test_get_publicacion_files_by_url_resolves_via_slug(httpx_mock):
    _mock_categories(httpx_mock)
    httpx_mock.add_response(
        url=f"{_API_BASE}/posts?slug=enemdu-anual",
        json=[
            {
                "id": 42,
                "link": "https://www.ecuadorencifras.gob.ec/enemdu-anual/",
                "date": "2026-02-26T00:00:00",
                "modified": "2026-02-26T00:00:00",
                "title": {"rendered": "ENEMDU Anual"},
                "categories": [],
                "content": {"rendered": ""},
            }
        ],
    )

    result = await inec_client.get_publicacion_files(
        "https://www.ecuadorencifras.gob.ec/enemdu-anual/"
    )

    assert result["id"] == 42
    assert result["archivos"] == []


@pytest.mark.asyncio
async def test_get_publicacion_files_rejects_foreign_url():
    with pytest.raises(ValueError, match="fuera de ecuadorencifras"):
        await inec_client.get_publicacion_files("https://example.com/post/")


@pytest.mark.asyncio
async def test_get_publicacion_files_raises_when_not_found(httpx_mock):
    httpx_mock.add_response(url=f"{_API_BASE}/posts?include=99999999", json=[])

    with pytest.raises(ValueError, match="No se encontró"):
        await inec_client.get_publicacion_files(99999999)


@pytest.mark.asyncio
async def test_get_api_json_raises_on_http_error(httpx_mock):
    httpx_mock.add_response(
        url=f"{_API_BASE}/posts?include=1",
        status_code=400,
        json={"message": "Parámetro inválido"},
    )

    with pytest.raises(ValueError, match="Parámetro inválido"):
        await inec_client.get_publicacion_files(1)


@pytest.mark.asyncio
async def test_get_topic_files_tags_year_and_filters(httpx_mock):
    topic_url = "https://www.ecuadorencifras.gob.ec/defunciones-generales-y-fetales-bases-de-datos/"
    base = "https://www.ecuadorencifras.gob.ec/documentos/datos/Poblacion_y_Demografia/"
    httpx_mock.add_response(
        url=topic_url,
        html=(
            "<title>Defunciones</title>"
            f'<a href="{base}def_generales/spss/dbd_defunciones_generales_1990_spss.zip">a</a>'
            f'<a href="{base}def_generales/spss/dbd_defunciones_generales_2015_spss.zip">b</a>'
        ),
    )
    allf = await inec_client.get_topic_files(topic_url)
    assert [f["year"] for f in allf["archivos"]] == [1990, 2015]
    only = await inec_client.get_topic_files(topic_url, year=2015)
    assert len(only["archivos"]) == 1
    assert only["archivos"][0]["year"] == 2015


def test_year_from_url_falls_back_to_folder():
    url = "https://x.ec/documentos/web-inec/Nacimientos_Defunciones/2018/BDD_spss.zip"
    assert inec_client._year_from_url(url) == 2018


@pytest.mark.asyncio
async def test_get_topic_files_does_not_cache_failed_related_pages(httpx_mock):
    bad = _BASE + "endi_desnutricion_bad/"
    httpx_mock.add_response(url=_HUB_URL, html=_hub_page("endi_desnutricion_bad"))
    httpx_mock.add_response(url=bad, status_code=500, content=b"boom")

    first = await inec_client.get_topic_files(_HUB_URL)

    assert first["archivos"] == []
    assert inec_client._topic_files_cache.get(_HUB_URL) is None

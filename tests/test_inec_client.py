import pytest

from helpers import inec_client

_SEED_URL = inec_client._SEED_PAGE_URL

_MENU_HTML = """
<html><body>
<ul>
<li><a class="mega-menu-link" href="https://www.ecuadorencifras.gob.ec/indice-de-precios-al-consumidor/">Índice de Precios al Consumidor</a></li>
<li><a class="mega-menu-link" href="https://www.ecuadorencifras.gob.ec/pobreza2/">Pobreza</a></li>
<li><a class="mega-menu-link" href="https://www.ecuadorencifras.gob.ec/indice-de-precios-al-consumidor/">Índice de Precios al Consumidor</a></li>
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


@pytest.fixture(autouse=True)
def clear_caches():
    inec_client._topics_cache.clear()
    inec_client._topic_files_cache.clear()
    yield
    inec_client._topics_cache.clear()
    inec_client._topic_files_cache.clear()


@pytest.mark.asyncio
async def test_search_topics(httpx_mock):
    httpx_mock.add_response(url=_SEED_URL, html=_MENU_HTML)

    result = await inec_client.search_topics(query="precios")

    assert result["total"] == 1
    assert result["total_temas"] == 2
    assert result["temas"][0]["nombre"] == "Índice de Precios al Consumidor"
    assert result["temas"][0]["url"] == (
        "https://www.ecuadorencifras.gob.ec/indice-de-precios-al-consumidor/"
    )


@pytest.mark.asyncio
async def test_search_topics_no_query_returns_all(httpx_mock):
    httpx_mock.add_response(url=_SEED_URL, html=_MENU_HTML)

    result = await inec_client.search_topics()

    assert result["total"] == 2
    assert result["total_temas"] == 2


@pytest.mark.asyncio
async def test_search_topics_dedupes_repeated_menu_entries(httpx_mock):
    httpx_mock.add_response(url=_SEED_URL, html=_MENU_HTML)

    topics = await inec_client._fetch_topics()

    urls = [t["url"] for t in topics]
    assert len(urls) == len(set(urls))


@pytest.mark.asyncio
async def test_get_topic_files(httpx_mock):
    topic_url = "https://www.ecuadorencifras.gob.ec/indice-de-precios-al-consumidor/"
    httpx_mock.add_response(url=topic_url, html=_TOPIC_HTML)

    result = await inec_client.get_topic_files(topic_url)

    assert result["titulo"] == "Índice de Precios al Consumidor – IPC"
    urls = [f["url"] for f in result["archivos"]]
    assert (
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/Boletin_Tecnico_2026.pdf" in urls
    )
    assert (
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/"
        "Tabulados_y_series_historicas_CSV.zip" in urls
    )
    # Files hosted off ecuadorencifras.gob.ec/documentos/ are not picked up.
    assert not any("gobiernoelectronico" in u for u in urls)

    formats = {f["url"]: f["format"] for f in result["archivos"]}
    assert formats[
        "https://www.ecuadorencifras.gob.ec/documentos/web-inec/Boletin_Tecnico_2026.pdf"
    ] == "PDF"


@pytest.mark.asyncio
async def test_get_topic_files_rejects_foreign_url():
    with pytest.raises(ValueError, match="fuera de ecuadorencifras"):
        await inec_client.get_topic_files("https://example.com/foo/")

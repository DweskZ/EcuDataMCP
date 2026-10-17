import httpx
import pytest

from helpers import eeq_cortes_client as client


def _card(title: str, desc: str) -> str:
    # Trimmed but structurally faithful copy of a real result card from
    # www.eeq.com.ec/search?q=horarios (confirmed live 2026-09-25).
    return (
        '<li class="card-page-item card-page-item-asset"><div class="card">'
        '<div class="card-body"><div class="card-row"><section>'
        f'<h3 class="card-title"><a href="https://www.eeq.com.ec/search?p_p_id=x">'
        f"{title}</a></h3>"
        '<p class="card-subtitle"><span>Daniel Antonio Pilco Vasco</span></p>'
        f'<p class="card-description">{desc}</p>'
        "</section></div></div></div></li>"
    )


_SEARCH_PAGE = (
    "<html><body><p>3 resultados para horarios</p><ul>"
    + _card(
        ' <span class="highlight mark">Horarios</span> del 15 al 17 de noviembre ',
        '<span class="highlight mark">Horarios</span> del 15 al 17 de noviembre false '
        "2024-11-14 https://www.eeq.com.ec/documents.../d/empresa-electrica-quito/vsd "
        '<span class="highlight mark">horarios</span> general',
    )
    + _card(
        "14 - 20 de octubre",
        "14 - 20 de octubre www.eeq.com.ec/documents/d/empresa-electrica-quito/"
        "14-al-20-10-2024 Descarga los horarios",
    )
    # A news article matching the query, with no linked document.
    + _card(
        "CONSEJOS PARA AHORRAR ENERGÍA",
        "Revise los horarios de mayor consumo en su hogar.",
    )
    # A live card for a slug that is also seeded must win over the seed.
    + _card(
        "Horarios del 04 al 06 de octubre",
        "Horarios del 04 al 06 de octubre false 2024-10-03 "
        "https://www.eeq.com.ec/documents.../d/empresa-electrica-quito/04-al-06-oct",
    )
    + "</ul></body></html>"
)


def _search_url(page_no: int) -> httpx.URL:
    return httpx.URL(
        client._SEARCH_URL,
        params={"q": "horarios", "delta": client._PAGE_SIZE, "start": page_no},
    )


@pytest.fixture(autouse=True)
def clear_cache():
    client._archivos_cache.clear()
    yield
    client._archivos_cache.clear()


def test_parse_search_page_keeps_only_cards_with_documents():
    archivos = client._parse_search_page(_SEARCH_PAGE)

    assert [a["slug"] for a in archivos] == ["vsd", "14-al-20-10-2024", "04-al-06-oct"]
    assert archivos[0]["periodo"] == "Horarios del 15 al 17 de noviembre"
    assert archivos[0]["fecha"] == "2024-11-14"
    assert archivos[1]["fecha"] is None


async def test_fetch_archivos_merges_live_results_with_seeds(httpx_mock):
    httpx_mock.add_response(url=_search_url(1), text=_SEARCH_PAGE)

    archivos = await client._fetch_archivos()

    by_slug = {a["slug"]: a for a in archivos}
    assert len(archivos) == len(client._SEED_ARCHIVOS) + 1
    assert by_slug["vsd"]["url"] == (
        "https://www.eeq.com.ec/documents/d/empresa-electrica-quito/vsd"
    )
    assert by_slug["04-al-06-oct"]["origen"] == "busqueda_sitio"
    assert by_slug["29_04_2024"]["origen"] == "semilla"


async def test_search_eeq_cortes_filters_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=_search_url(1), text=_SEARCH_PAGE)

    result = await client.search_eeq_cortes(query="sabado")

    assert result["total"] == 1
    assert result["archivos"][0]["slug"] == "mf-09-10-nov"


async def test_search_eeq_cortes_filters_by_year(httpx_mock):
    httpx_mock.add_response(url=_search_url(1), text=_SEARCH_PAGE)

    result = await client.search_eeq_cortes(query="2023")

    assert result["total"] == 3
    assert all(a["fecha"].startswith("2023") for a in result["archivos"])


async def test_seed_only_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=_search_url(1), text="<html>0 resultados</html>")
    httpx_mock.add_response(url=_search_url(1), text=_SEARCH_PAGE)

    first = await client._fetch_archivos()
    assert len(first) == len(client._SEED_ARCHIVOS)

    second = await client._fetch_archivos()
    assert len(second) == len(client._SEED_ARCHIVOS) + 1


async def test_search_page_without_result_list_raises_and_is_not_cached(httpx_mock):
    # No cards and no "N resultados" count: an anti-bot/maintenance page or
    # a redesign, not a genuine empty search -- must not silently fall back
    # to the seed list as if the live search had been consulted.
    httpx_mock.add_response(
        url=_search_url(1), text="<html><body>Access denied</body></html>"
    )
    httpx_mock.add_response(url=_search_url(1), text=_SEARCH_PAGE)

    with pytest.raises(ValueError, match="EEQ"):
        await client._fetch_archivos()

    second = await client._fetch_archivos()
    assert len(second) == len(client._SEED_ARCHIVOS) + 1


async def test_concurrent_cache_misses_parse_pdf_once(monkeypatch):
    import asyncio

    client._horarios_cache.clear()
    calls = {"download": 0, "parse": 0}

    async def fake_download(url, max_bytes):
        calls["download"] += 1
        await asyncio.sleep(0.01)
        return b"%PDF-fake", False

    def fake_parse(raw):
        calls["parse"] += 1
        return {"filas": [], "paginas": 1}

    monkeypatch.setattr(client, "download_bytes", fake_download)
    monkeypatch.setattr(client, "parse_pdf", fake_parse)

    await asyncio.gather(*(client._load_horarios("vsd", "https://x/vsd") for _ in range(5)))

    assert calls == {"download": 1, "parse": 1}
    assert client._fill_locks == {}

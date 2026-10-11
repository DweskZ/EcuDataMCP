import asyncio

import pytest

from helpers import bvq_client as client

# Trimmed excerpts of the real pages (confirmed live 2026-10-10): the
# download buttons are icon-only links, absolute on the boletines pages and
# site-relative on valoracion/emisores, mixed with normativa and marketing
# PDFs and a foreign-host link that must not be listed.
_COTIZACIONES = """
<div class="threeD-content-inner"><a href="https://www.bolsadequito.com/uploads/estadisticas/boletines/cotizaciones-historicas/notas-credito.xls" style="x"><i class="fa fa-download"></i></a></div>
<div class="threeD-content-inner"><a href="https://www.bolsadequito.com/uploads/estadisticas/boletines/cotizaciones-historicas/acciones.xls"><i></i></a></div>
<a href="https://www.bolsadequito.com/uploads/estadisticas/boletines/cotizaciones-historicas/acciones.xls">dup</a>
<a href="/uploads/normativa/mercado-de-valores/ley-de-mercado-de-valores.pdf">Ley</a>
<a href="https://www.bolsadequito.com/documentos/marketing/guia_bonos_verdes.pdf">Guia</a>
<a href="https://otro.example.com/uploads/estadisticas/x.xls">fuera</a>
"""
_VECTOR_DIARIO = (
    '<a href="/uploads/estadisticas/valoracion/vector-precios-diario/'
    'vector-precios-diario.xls"><i></i></a>'
)
_VECTOR_MENSUAL = (
    '<a href="/uploads/estadisticas/valoracion/vector-precios-mensual/'
    'vector-precios-mensual.xls"><i></i></a>'
)
_EMPTY = "<html>sin archivos</html>"

_COT_BASE = f"{client._BASE}/uploads/estadisticas/boletines/cotizaciones-historicas"


@pytest.fixture(autouse=True)
def clear_cache():
    client._seccion_cache.clear()
    yield
    client._seccion_cache.clear()


def _mock_probe(httpx_mock, url, *, total, last_modified):
    httpx_mock.add_response(
        url=url,
        status_code=206,
        content=b"P",
        headers={
            "Content-Range": f"bytes 0-0/{total}",
            "Last-Modified": last_modified,
        },
    )


def test_list_secciones_covers_every_section():
    secciones = client.list_secciones()
    assert len(secciones) == 10
    assert secciones[0]["seccion"] == "cotizaciones_historicas"
    assert all(s["url"].startswith("https://www.bolsadequito.com/") for s in secciones)


def test_titulo_from_file_name():
    assert client._titulo_from_url(f"{_COT_BASE}/notas-credito.xls") == "Notas credito"
    assert (
        client._titulo_from_url(f"{client._BASE}/uploads/x/curva_spot.xls")
        == "Curva spot"
    )


@pytest.mark.asyncio
async def test_cotizaciones_filters_foreign_links_and_adds_freshness(httpx_mock):
    httpx_mock.add_response(
        url=f"{client._EST}/boletines-2/cotizaciones-historicas", html=_COTIZACIONES
    )
    _mock_probe(
        httpx_mock,
        f"{_COT_BASE}/notas-credito.xls",
        total=3607552,
        last_modified="Thu, 08 Oct 2026 21:08:28 GMT",
    )
    _mock_probe(
        httpx_mock,
        f"{_COT_BASE}/acciones.xls",
        total=1707008,
        last_modified="Thu, 08 Oct 2026 21:08:30 GMT",
    )

    result = await client.get_seccion_archivos("cotizaciones_historicas")

    assert [a["titulo"] for a in result["archivos"]] == ["Notas credito", "Acciones"]
    acciones = result["archivos"][1]
    assert acciones["formato"] == "XLS"
    assert acciones["tamano_bytes"] == 1707008
    assert acciones["modificado"] == "2026-10-08T21:08:30+00:00"
    assert acciones["pagina"].endswith("/boletines-2/cotizaciones-historicas")


@pytest.mark.asyncio
async def test_valoracion_merges_pages_and_resolves_relative_hrefs(httpx_mock):
    pages = {
        "vector-de-precios-diario": _VECTOR_DIARIO,
        "vector-de-precios-mensual": _VECTOR_MENSUAL,
        "precio-nacional-renta-variable-diario": _EMPTY,
        "precio-nacional-renta-variable-mensual": _EMPTY,
        "tasa-spot": _EMPTY,
    }
    for page, html in pages.items():
        httpx_mock.add_response(url=f"{client._EST}/valoracion/{page}", html=html)
    for name in ("vector-precios-diario", "vector-precios-mensual"):
        _mock_probe(
            httpx_mock,
            f"{client._BASE}/uploads/estadisticas/valoracion/{name}/{name}.xls",
            total=1183232,
            last_modified="Thu, 08 Oct 2026 22:25:48 GMT",
        )

    result = await client.get_seccion_archivos("valoracion")

    assert result["total"] == 2
    assert all(
        a["url"].startswith("https://www.bolsadequito.com/") for a in result["archivos"]
    )


@pytest.mark.asyncio
async def test_empty_section_is_not_cached(httpx_mock):
    httpx_mock.add_response(
        url=f"{client._EST}/boletines/analisis-de-sensibilidad", html=_EMPTY
    )

    result = await client.get_seccion_archivos("analisis_sensibilidad")

    assert result["total"] == 0
    assert client._seccion_cache.get("analisis_sensibilidad") is None


@pytest.mark.asyncio
async def test_unknown_seccion_raises():
    with pytest.raises(ValueError, match="no reconocida"):
        await client.get_seccion_archivos("nope")


@pytest.mark.asyncio
async def test_slow_section_does_not_block_another(monkeypatch):
    release = asyncio.Event()

    async def fake_fetch(url):
        if "cotizaciones-historicas" in url:
            await release.wait()
            return _COTIZACIONES
        return _VECTOR_DIARIO

    async def fake_probe(archivos):
        return None

    monkeypatch.setattr(client, "fetch_html", fake_fetch)
    monkeypatch.setattr(client, "probe_archivos", fake_probe)

    slow = asyncio.create_task(client.get_seccion_archivos("cotizaciones_historicas"))
    await asyncio.sleep(0)
    fast = await asyncio.wait_for(client.get_seccion_archivos("sector_publico"), timeout=2)

    assert fast["total"] == 1
    assert not slow.done()
    release.set()
    assert (await slow)["total"] == 2


@pytest.mark.asyncio
async def test_concurrent_calls_for_one_section_share_one_fill(monkeypatch):
    fetched = []

    async def fake_fetch(url):
        fetched.append(url)
        await asyncio.sleep(0.05)
        return _COTIZACIONES

    async def fake_probe(archivos):
        return None

    monkeypatch.setattr(client, "fetch_html", fake_fetch)
    monkeypatch.setattr(client, "probe_archivos", fake_probe)

    first, second = await asyncio.gather(
        client.get_seccion_archivos("cotizaciones_historicas"),
        client.get_seccion_archivos("cotizaciones_historicas"),
    )

    assert first is second
    assert len(fetched) == 1

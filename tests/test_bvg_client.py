import asyncio

import pytest

from helpers import bvg_client as client

# Trimmed excerpt of the real home page (confirmed live 2026-10-10). It keeps
# the page's quirks: &nbsp; before the labels, Titularizaciones linked twice
# (second label "VTC"), and files of several groups in the same markup.
_HOME_HTML = """
<html><body>
<a href="/bvg/codigo-de-etica-BVG-2022.pdf">Código de ética</a>
<a href="/boletines/historicos/dividendos-totales.xlsx" class="x"><i></i>&nbsp;Dividendos Entregados</a>
<a href="/boletines/valoracion/valores-permitidos.xlsx">&nbsp; Valores Permitidos</a>
<a href="/boletines/historicos/BVG_Acciones.xlsx">&nbsp; Acciones</a>
<a href="/boletines/historicos/BVG_Titularizaciones.xlsx">&nbsp; Titularizaciones</a>
<a href="/boletines/historicos/BVG_NotasDeCredito.xlsx">&nbsp; Notas de Crédito</a>
<a href="/boletines/historicos/BVG_BonosDelEstado.xlsx">Bonos</a>
<a href="/boletines/historicos/BVG_Titularizaciones.xlsx">&nbsp; VTC</a>
<a href="/ofertas-publicas/files/vigente-en-circulacion.xls">&nbsp; Vigente en Circulación</a>
<a href="/ofertas-publicas/files/oferta-publica-saldos-vigentes.xls">Con saldos disponibles</a>
</body></html>
"""

_ACCIONES = f"{client._BASE}/boletines/historicos/BVG_Acciones.xlsx"


@pytest.fixture(autouse=True)
def clear_caches():
    client._page_cache.clear()
    client._seccion_cache.clear()
    yield
    client._page_cache.clear()
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


def test_list_secciones_hides_internal_prefix():
    secciones = client.list_secciones()
    assert [s["seccion"] for s in secciones] == [
        "historicos",
        "dividendos",
        "valoracion",
        "ofertas_publicas",
    ]
    assert all("prefijo" not in s for s in secciones)


@pytest.mark.asyncio
async def test_historicos_lists_trading_files_with_freshness(httpx_mock):
    httpx_mock.add_response(url=f"{client._BASE}/", html=_HOME_HTML)
    for name, total in [
        ("BVG_Acciones", 1433675),
        ("BVG_Titularizaciones", 255894),
        ("BVG_NotasDeCredito", 3066265),
        ("BVG_BonosDelEstado", 3014774),
    ]:
        _mock_probe(
            httpx_mock,
            f"{client._BASE}/boletines/historicos/{name}.xlsx",
            total=total,
            last_modified="Thu, 08 Oct 2026 20:35:40 GMT",
        )

    result = await client.get_seccion_archivos("historicos")

    titulos = [a["titulo"] for a in result["archivos"]]
    # Titularizaciones is linked twice; the first label wins and it is listed once.
    assert titulos == ["Acciones", "Titularizaciones", "Notas de Crédito", "Bonos"]
    acciones = result["archivos"][0]
    assert acciones["url"] == _ACCIONES
    assert acciones["formato"] == "XLSX"
    assert acciones["tamano_bytes"] == 1433675
    assert acciones["modificado"] == "2026-10-08T20:35:40+00:00"
    # Dividends and valuation files are other sections.
    assert not any("dividendos" in a["url"] for a in result["archivos"])


@pytest.mark.asyncio
async def test_ofertas_publicas_are_xls(httpx_mock):
    httpx_mock.add_response(url=f"{client._BASE}/", html=_HOME_HTML)
    for name in ("vigente-en-circulacion", "oferta-publica-saldos-vigentes"):
        _mock_probe(
            httpx_mock,
            f"{client._BASE}/ofertas-publicas/files/{name}.xls",
            total=102912,
            last_modified="Thu, 08 Oct 2026 16:50:48 GMT",
        )

    result = await client.get_seccion_archivos("ofertas_publicas")

    assert result["total"] == 2
    assert {a["formato"] for a in result["archivos"]} == {"XLS"}


@pytest.mark.asyncio
async def test_failed_probe_keeps_the_listing(httpx_mock):
    httpx_mock.add_response(url=f"{client._BASE}/", html=_HOME_HTML)
    httpx_mock.add_response(
        url=f"{client._BASE}/boletines/valoracion/valores-permitidos.xlsx",
        status_code=404,
    )

    result = await client.get_seccion_archivos("valoracion")

    assert result["total"] == 1
    assert result["archivos"][0]["modificado"] is None
    assert result["archivos"][0]["tamano_bytes"] is None


@pytest.mark.asyncio
async def test_unknown_seccion_raises():
    with pytest.raises(ValueError, match="no reconocida"):
        await client.get_seccion_archivos("nope")


@pytest.mark.asyncio
async def test_page_without_links_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=f"{client._BASE}/", html="<html>Mantenimiento</html>")

    result = await client.get_seccion_archivos("dividendos")

    assert result["total"] == 0
    assert client._page_cache.get("html") is None
    assert client._seccion_cache.get("dividendos") is None


@pytest.mark.asyncio
async def test_slow_section_does_not_block_another(httpx_mock, monkeypatch):
    httpx_mock.add_response(url=f"{client._BASE}/", html=_HOME_HTML, is_reusable=True)
    release = asyncio.Event()

    async def fake_probe(archivos):
        # Only the historicos section is slow.
        if any("/historicos/BVG_" in a["url"] for a in archivos):
            await release.wait()

    monkeypatch.setattr(client, "probe_archivos", fake_probe)

    slow = asyncio.create_task(client.get_seccion_archivos("historicos"))
    await asyncio.sleep(0)
    fast = await asyncio.wait_for(client.get_seccion_archivos("valoracion"), timeout=2)

    assert fast["total"] == 1
    assert not slow.done()
    release.set()
    assert (await slow)["total"] == 4


@pytest.mark.asyncio
async def test_concurrent_calls_for_one_section_share_one_fill(httpx_mock, monkeypatch):
    httpx_mock.add_response(url=f"{client._BASE}/", html=_HOME_HTML, is_reusable=True)
    probes = []

    async def fake_probe(archivos):
        probes.append(len(archivos))
        await asyncio.sleep(0.05)

    monkeypatch.setattr(client, "probe_archivos", fake_probe)

    first, second = await asyncio.gather(
        client.get_seccion_archivos("historicos"), client.get_seccion_archivos("historicos")
    )

    assert first is second
    assert probes == [4]
    # The shared home page was fetched once as well.
    assert len(httpx_mock.get_requests()) == 1

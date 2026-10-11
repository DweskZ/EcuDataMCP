import pytest

from helpers import petroecuador_client as client

# Trimmed excerpt of the real https://www.eppetroecuador.ec/?p=3721 markup
# (fetched live 2026-10-10): Headerinfo blocks followed by a paleta list.
# Covers a direct PDF, a download.php link (absolute and relative, with
# &amp;force=0), a link whose text embeds markup and a daily figure, a
# text-only <li>, an internal ?p= page, the intranet subdomain and an
# off-domain link that must be dropped.
_CIFRAS_HTML = """
<html><body><section id="postcontent">
<div class="infoWraper">
<div class="bloqueInformativo">
<div class="Headerinfo"><a name="Informe2"></a>Informes Estadísticos Anuales</div>
<div class="paleta">
<ul>
<li><a href="https://www.eppetroecuador.ec/wp-content/plugins/download-monitor/download.php?id=3860">2025</a></li>
<li><a href="https://www.eppetroecuador.ec/wp-content/uploads/2024/06/INFORME-ESTADISTICO-ANUAL-2022.pdf">2022</a></li>
<li><a href="wp-content/plugins/download-monitor/download.php?id=25&amp;force=0">2012</a></li>
<li><a href="wp-content/plugins/download-monitor/download.php?id=2337">2017 &#8211; Informe estadístico 45 años</a></li>
</ul>
</div>
</div>
<div class="bloqueInformativo">
<div class="Headerinfo"><a name="Informe4"></a>Exploración y Producción</div>
<div class="paleta">
<ul>
<li><a href="https://www.eppetroecuador.ec/wp-content/plugins/download-monitor/download.php?id=3873">Producción de Campo BPPD:<span style="color: #808080;"> 356,570 Bls (Fecha efectiva: 09-octubre-2026</span><span style="color: #808080;">)</span></a></li>
<li>Costo de Producción por Barril:  <span style="color: #808080;">Junio 2025 | USD 27.61*</span></li>
<li><a href="https://example.com/otro.pdf">Fuera de dominio</a></li>
</ul>
</div>
</div>
<div class="bloqueInformativo">
<div class="Headerinfo"><a name="Informe3"></a>Comercialización</div>
<div class="paleta">
<ul>
<li><a href="https://www.eppetroecuador.ec/?p=8062">Precios de Venta en Terminales</a></li>
<li><a href="http://eppintranet.eppetroecuador.ec/idc/groups/public/documents/informes_estadisticos/files_informes/AnalisisDeStockPorTerminalProducto.pdf">Análisis de Stock por Terminal y Producto</a></li>
</ul>
</div>
</div>
</div></section></body></html>
"""


@pytest.fixture(autouse=True)
def clear_cache():
    client._page_cache.clear()
    yield
    client._page_cache.clear()


@pytest.mark.asyncio
async def test_list_categorias_counts_links_per_section(httpx_mock):
    httpx_mock.add_response(url=client._CIFRAS_URL, html=_CIFRAS_HTML)

    result = await client.list_categorias()

    assert result["total"] == 3
    counts = {c["id"]: c["total_archivos"] for c in result["categorias"]}
    # The off-domain link and the text-only <li> are not files.
    assert counts == {
        "informes_estadisticos_anuales": 4,
        "exploracion_y_produccion": 1,
        "comercializacion": 2,
    }


@pytest.mark.asyncio
async def test_get_categoria_resolves_relative_links_and_formats(httpx_mock):
    httpx_mock.add_response(url=client._CIFRAS_URL, html=_CIFRAS_HTML)

    result = await client.get_categoria_archivos("Informes Estadísticos Anuales")

    by_title = {a["titulo"]: a for a in result["archivos"]}
    assert by_title["2022"]["formato"] == "PDF"
    assert by_title["2025"]["formato"] == "DESCONOCIDO"
    assert by_title["2012"]["url"] == (
        "https://www.eppetroecuador.ec/wp-content/plugins/download-monitor/"
        "download.php?id=25&force=0"
    )
    assert by_title["2017 – Informe estadístico 45 años"]["url"].startswith(
        "https://www.eppetroecuador.ec/wp-content/plugins/"
    )


@pytest.mark.asyncio
async def test_get_categoria_keeps_daily_figure_title_and_drops_foreign_links(httpx_mock):
    httpx_mock.add_response(url=client._CIFRAS_URL, html=_CIFRAS_HTML)

    result = await client.get_categoria_archivos("exploracion_y_produccion")

    assert result["total"] == 1
    assert result["archivos"][0]["titulo"] == (
        "Producción de Campo BPPD: 356,570 Bls (Fecha efectiva: 09-octubre-2026)"
    )


@pytest.mark.asyncio
async def test_page_and_intranet_links_are_kept(httpx_mock):
    httpx_mock.add_response(url=client._CIFRAS_URL, html=_CIFRAS_HTML)

    result = await client.get_categoria_archivos("Comercialización")

    formatos = {a["titulo"]: a["formato"] for a in result["archivos"]}
    assert formatos["Precios de Venta en Terminales"] == "HTML"
    assert formatos["Análisis de Stock por Terminal y Producto"] == "PDF"


@pytest.mark.asyncio
async def test_unknown_section_lists_valid_ones(httpx_mock):
    httpx_mock.add_response(url=client._CIFRAS_URL, html=_CIFRAS_HTML)

    with pytest.raises(ValueError, match="comercializacion"):
        await client.get_categoria_archivos("inexistente")


@pytest.mark.asyncio
async def test_broken_page_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=client._CIFRAS_URL, html="<html>mantenimiento</html>")

    result = await client.list_categorias()

    assert result["total"] == 0
    assert client._page_cache.get("html") is None

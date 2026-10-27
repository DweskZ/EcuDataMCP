import pytest

from helpers import cenace_biblioteca_client as client

# Trimmed excerpt of https://www.cenace.gob.ec/biblioteca/ (checked live
# 2026-10-26): top-level categories nesting one level by year, one entry
# repeated within a category, one link on a foreign host, an empty category.
_LINK = "https://www.cenace.gob.ec/wp-content/plugins/download-monitor/download.php"
_BIBLIOTECA_HTML = f"""
<html><body>
<ul class="ul-downloads">

<li class="li-gray1" id="cat-1049" >
    <a style="display: block;"><span class="ico">+</span>Informes de Gestión</a>
    <ul><li class="li-gray1" id="cat-3001" >
        <a style="display: block;"><span class="ico">+</span>2026</a>
        <ul><li class="li-gray4"><div><span class="titulo">Informe Ejecutivo julio 2026</span>
        <a href="{_LINK}?id=4700&force=0" title="Ver Informe Ejecutivo julio 2026" class="ver">ver</a>
        <a href="{_LINK}?id=4700&force=1" title="Descargar Informe Ejecutivo julio 2026">descarga</a>
        <a href="{_LINK}?id=4700&force=1" title="Descargar Informe Ejecutivo julio 2026">descarga</a>
        </div></li></ul>
    </li>
    <li class="li-gray1" id="cat-3002" >
        <a style="display: block;"><span class="ico">+</span>2025</a>
        <ul><li class="li-gray4"><div>
        <a href="{_LINK}?id=4500&amp;force=1" title="Descargar Informe Ejecutivo diciembre 2025">descarga</a>
        <a href="https://evil.example.com/cenace.gob.ec/wp-content/plugins/download-monitor/download.php?id=9&force=1" title="Descargar Falso">x</a>
        </div></li></ul>
    </li></ul>
</li>
<li class="li-gray1" id="cat-1076" >
    <a style="display: block;"><span class="ico">+</span>Información del Sector Eléctrico</a>
    <ul><li class="li-gray4"><div>
    <a href="{_LINK}?id=4100&force=1" title="Descargar Factor de Emisión de CO2 2024">descarga</a>
    </div></li></ul>
</li>
<li class="li-gray1" id="cat-1073" >
    <a style="display: block;"><span class="ico">+</span>Concursos de Mérito y Oposición</a>
    <ul></ul>
</li>
</ul>
</body></html>
"""


@pytest.fixture(autouse=True)
def clear_cache():
    client._page_cache.clear()
    yield
    client._page_cache.clear()


async def test_list_categorias_counts_top_level_only(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    result = await client.list_biblioteca_categorias()

    assert [(c["id"], c["nombre"]) for c in result["categorias"]] == [
        ("1049", "Informes de Gestión"),
        ("1076", "Información del Sector Eléctrico"),
        ("1073", "Concursos de Mérito y Oposición"),
    ]
    assert [c["total_archivos"] for c in result["categorias"]] == [4, 1, 0]
    assert result["url_fuente"] == client._BIBLIOTECA_URL


async def test_get_categoria_tags_year_dedupes_and_drops_foreign_hosts(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    result = await client.get_biblioteca_categoria_archivos("informes de gestion")

    assert result["id"] == "1049"
    assert [(a["id"], a["subgrupo"], a["titulo"]) for a in result["archivos"]] == [
        ("4700", "2026", "Informe Ejecutivo julio 2026"),
        ("4500", "2025", "Informe Ejecutivo diciembre 2025"),
    ]
    assert result["archivos"][1]["url"] == f"{_LINK}?id=4500&force=1"
    assert all(a["formato"] == "DESCONOCIDO" for a in result["archivos"])


async def test_get_categoria_rejects_unknown_name(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    with pytest.raises(ValueError, match="1049:Informes de Gestión"):
        await client.get_biblioteca_categoria_archivos("no existe")


async def test_maintenance_page_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html="<p>mantenimiento</p>")
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    assert (await client.list_biblioteca_categorias())["total"] == 0
    assert (await client.list_biblioteca_categorias())["total"] == 3

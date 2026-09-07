import pytest

from helpers import arcsa_client as client

# Trimmed but structurally faithful excerpt of the real
# https://www.controlsanitario.gob.ec/base-de-datos/ markup (confirmed live
# 2026-09-05): a "ul-downloads" root holding top-level "li-gray1" category
# items (id="cat-N"), same download-monitor pattern as SGR's Biblioteca.
# Includes a flat category, a category nesting one sub-category level (by
# year, mirroring the real "Inspecciones en Establecimientos Farmacéuticos
# Controlados" > year sub-categories), and an empty category with no
# entries at all (two of these exist on the real page).
_BASE_DATOS_HTML = """
<html><body>
<ul class="ul-downloads">
<li class="li-gray1" id="cat-64">
    <a style="display: block;"><span class="ico">+</span>Alimentos</a>
    <ul><li class="li-gray4"><div><div><span class="titulo">ARCSA_LISTADO DE ALIMENTOS 2026</span></div>
    <div><span class="link">
    <a href="https://www.controlsanitario.gob.ec/wp-content/plugins/download-monitor/download.php?id=15870&amp;force=0" title="Ver ARCSA_LISTADO DE ALIMENTOS 2026" target="_blank" class="ver">ver</a>&nbsp;
    <a href="https://www.controlsanitario.gob.ec/wp-content/plugins/download-monitor/download.php?id=15870&amp;force=1" title="Descargar ARCSA_LISTADO DE ALIMENTOS 2026">descarga</a>
    </span></div></div></li></ul>
</li>
<li class="li-gray1" id="cat-401">
    <a style="display: block;"><span class="ico">+</span>Inspecciones en Establecimientos Farmacéuticos Controlados</a>
    <ul><li class="li-gray1" id="cat-1942">
        <a style="display: block;"><span class="ico">+</span>Establecimientos Farmacéuticos Controlados Año 2022</a>
        <ul><li class="li-gray4"><div><div><span class="titulo">Listado 2022</span></div>
        <div><span class="link">
        <a href="https://www.controlsanitario.gob.ec/wp-content/plugins/download-monitor/download.php?id=14090&amp;force=0" title="Ver Listado 2022" target="_blank" class="ver">ver</a>&nbsp;
        <a href="https://www.controlsanitario.gob.ec/wp-content/plugins/download-monitor/download.php?id=14090&amp;force=1" title="Descargar Listado 2022">descarga</a>
        </span></div></div></li></ul>
    </li>
    <li class="li-gray1" id="cat-1943">
        <a style="display: block;"><span class="ico">+</span>Establecimientos Farmacéuticos Controlados Año 2023</a>
        <ul><li class="li-gray4"><div><div><span class="titulo">Listado 2023</span></div>
        <div><span class="link">
        <a href="https://www.controlsanitario.gob.ec/wp-content/plugins/download-monitor/download.php?id=14091&amp;force=0" title="Ver Listado 2023" target="_blank" class="ver">ver</a>&nbsp;
        <a href="https://www.controlsanitario.gob.ec/wp-content/plugins/download-monitor/download.php?id=14091&amp;force=1" title="Descargar Listado 2023">descarga</a>
        </span></div></div></li></ul>
    </li></ul>
</li>
<li class="li-gray1" id="cat-461">
    <a style="display: block;"><span class="ico">+</span>Medicamentos incluidos en el certificado sanitario de provisión de medicamentos</a>
    <ul></ul>
</li>
</ul>
</body></html>
"""

_EMPTY_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    client._page_cache.clear()
    yield
    client._page_cache.clear()


@pytest.mark.asyncio
async def test_list_categorias_returns_only_top_level(httpx_mock):
    httpx_mock.add_response(url=client._BASE_DATOS_URL, html=_BASE_DATOS_HTML)

    result = await client.list_categorias()

    assert result["total"] == 3
    nombres = {c["nombre"]: c for c in result["categorias"]}
    assert "Alimentos" in nombres
    assert "Inspecciones en Establecimientos Farmacéuticos Controlados" in nombres
    # The nested year sub-categories must not appear as their own
    # top-level entries.
    assert "Establecimientos Farmacéuticos Controlados Año 2022" not in nombres
    assert "Establecimientos Farmacéuticos Controlados Año 2023" not in nombres

    assert nombres["Alimentos"]["total_archivos"] == 1
    assert (
        nombres["Inspecciones en Establecimientos Farmacéuticos Controlados"][
            "total_archivos"
        ]
        == 2
    )
    # An empty category is listed, not hidden.
    assert (
        nombres[
            "Medicamentos incluidos en el certificado sanitario de provisión de medicamentos"
        ]["total_archivos"]
        == 0
    )


@pytest.mark.asyncio
async def test_get_categoria_archivos_flat_category(httpx_mock):
    httpx_mock.add_response(url=client._BASE_DATOS_URL, html=_BASE_DATOS_HTML)

    result = await client.get_categoria_archivos("Alimentos")

    assert result["total"] == 1
    archivo = result["archivos"][0]
    assert archivo["id"] == "15870"
    assert archivo["subgrupo"] is None
    assert archivo["formato"] == "DESCONOCIDO"
    assert archivo["titulo"] == "ARCSA_LISTADO DE ALIMENTOS 2026"


@pytest.mark.asyncio
async def test_get_categoria_archivos_nested_by_year(httpx_mock):
    httpx_mock.add_response(url=client._BASE_DATOS_URL, html=_BASE_DATOS_HTML)

    result = await client.get_categoria_archivos("401")

    assert (
        result["nombre"] == "Inspecciones en Establecimientos Farmacéuticos Controlados"
    )
    assert result["total"] == 2
    by_title = {a["titulo"]: a for a in result["archivos"]}
    assert (
        by_title["Listado 2022"]["subgrupo"]
        == "Establecimientos Farmacéuticos Controlados Año 2022"
    )
    assert (
        by_title["Listado 2023"]["subgrupo"]
        == "Establecimientos Farmacéuticos Controlados Año 2023"
    )


@pytest.mark.asyncio
async def test_get_categoria_archivos_empty_category(httpx_mock):
    httpx_mock.add_response(url=client._BASE_DATOS_URL, html=_BASE_DATOS_HTML)

    result = await client.get_categoria_archivos(
        "Medicamentos incluidos en el certificado sanitario de provisión de medicamentos"
    )

    assert result["total"] == 0
    assert result["archivos"] == []


@pytest.mark.asyncio
async def test_get_categoria_archivos_unknown_raises(httpx_mock):
    httpx_mock.add_response(url=client._BASE_DATOS_URL, html=_BASE_DATOS_HTML)

    with pytest.raises(ValueError):
        await client.get_categoria_archivos("no-existe")


@pytest.mark.asyncio
async def test_empty_scrape_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=client._BASE_DATOS_URL, html=_EMPTY_HTML)
    httpx_mock.add_response(url=client._BASE_DATOS_URL, html=_BASE_DATOS_HTML)

    first = await client.list_categorias()
    assert first["total"] == 0

    second = await client.list_categorias()
    assert second["total"] == 3

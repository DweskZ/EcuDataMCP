import pytest

from helpers import senescyt_biblioteca_client as client

# Trimmed but structurally faithful excerpt of the real
# https://educacion.gob.ec/edusuperior/biblioteca/ markup (confirmed live
# 2026-09-10): a "ul-downloads" root holding top-level "li-gray1" category
# items (id="cat-N"), same download-monitor pattern as SGR's Biblioteca and
# ARCSA's Base de Registros Emitidos. Includes a flat category, a category
# nesting one sub-category level (by year), a category nesting THREE levels
# (confirmed real on this page under Normativa/Acuerdos, deeper than either
# prior instance), and an empty category.
_BIBLIOTECA_HTML = """
<html><body>
<ul class="ul-downloads">
<li class="li-gray1" id="cat-277">
    <a style="display: block;"><span class="ico">+</span>Indicadores ACTI</a>
    <ul><li class="li-gray4"><div><div><span class="titulo">Indicadores ACTI 2021</span></div>
    <div><span class="link">
    <a href="https://educacion.gob.ec/edusuperior/wp-content/plugins/download-monitor/download.php?id=8012&amp;force=0" title="Ver Indicadores ACTI 2021" target="_blank" class="ver">ver</a>&nbsp;
    <a href="https://educacion.gob.ec/edusuperior/wp-content/plugins/download-monitor/download.php?id=8012&amp;force=1" title="Descargar Indicadores ACTI 2021">descarga</a>
    </span></div></div></li></ul>
</li>
<li class="li-gray1" id="cat-3976">
    <a style="display: block;"><span class="ico">+</span>PAC SENESCYT 2025</a>
    <ul><li class="li-gray1" id="cat-3977">
        <a style="display: block;"><span class="ico">+</span>Enero 2025</a>
        <ul><li class="li-gray4"><div><div><span class="titulo">PAC Enero 2025</span></div>
        <div><span class="link">
        <a href="https://educacion.gob.ec/edusuperior/wp-content/plugins/download-monitor/download.php?id=9001&amp;force=0" title="Ver PAC Enero 2025" target="_blank" class="ver">ver</a>&nbsp;
        <a href="https://educacion.gob.ec/edusuperior/wp-content/plugins/download-monitor/download.php?id=9001&amp;force=1" title="Descargar PAC Enero 2025">descarga</a>
        </span></div></div></li></ul>
    </li></ul>
</li>
<li class="li-gray1" id="cat-120">
    <a style="display: block;"><span class="ico">+</span>Normativa</a>
    <ul><li class="li-gray1" id="cat-3052">
        <a style="display: block;"><span class="ico">+</span>Reglamento de Servicios de Registro de Títulos</a>
        <ul><li class="li-gray1" id="cat-3053">
            <a style="display: block;"><span class="ico">+</span>a. Documento inicial</a>
            <ul><li class="li-gray4"><div><div><span class="titulo">Reglamento de Registro de Títulos</span></div>
            <div><span class="link">
            <a href="https://educacion.gob.ec/edusuperior/wp-content/plugins/download-monitor/download.php?id=7388&amp;force=0" title="Ver Reglamento de Registro de Títulos" target="_blank" class="ver">ver</a>&nbsp;
            <a href="https://educacion.gob.ec/edusuperior/wp-content/plugins/download-monitor/download.php?id=7388&amp;force=1" title="Descargar Reglamento de Registro de Títulos">descarga</a>
            </span></div></div></li></ul>
        </li></ul>
    </li></ul>
</li>
<li class="li-gray1" id="cat-24">
    <a style="display: block;"><span class="ico">+</span>Acuerdos</a>
    <ul><li class="li-gray4"><div><div><span class="titulo">Acuerdo compartido entre dos categorías</span></div>
    <div><span class="link">
    <a href="https://educacion.gob.ec/edusuperior/wp-content/plugins/download-monitor/download.php?id=8012&amp;force=0" title="Ver Acuerdo compartido entre dos categorías" target="_blank" class="ver">ver</a>&nbsp;
    <a href="https://educacion.gob.ec/edusuperior/wp-content/plugins/download-monitor/download.php?id=8012&amp;force=1" title="Descargar Acuerdo compartido entre dos categorías">descarga</a>
    </span></div></div></li></ul>
</li>
<li class="li-gray1" id="cat-766">
    <a style="display: block;"><span class="ico">+</span>Mecanismo de Participación Ciudadana</a>
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
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    result = await client.list_biblioteca_categorias()

    assert result["total"] == 5
    nombres = {c["nombre"]: c for c in result["categorias"]}
    assert "Indicadores ACTI" in nombres
    assert "PAC SENESCYT 2025" in nombres
    assert "Normativa" in nombres
    # Nested sub-categories, at any depth, must not appear as their own
    # top-level entries.
    assert "Enero 2025" not in nombres
    assert "Reglamento de Servicios de Registro de Títulos" not in nombres
    assert "a. Documento inicial" not in nombres

    assert nombres["Indicadores ACTI"]["total_archivos"] == 1
    assert nombres["PAC SENESCYT 2025"]["total_archivos"] == 1
    assert nombres["Normativa"]["total_archivos"] == 1
    # An empty category is listed, not hidden.
    assert nombres["Mecanismo de Participación Ciudadana"]["total_archivos"] == 0


@pytest.mark.asyncio
async def test_get_categoria_archivos_flat_category(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    result = await client.get_biblioteca_categoria_archivos("Indicadores ACTI")

    assert result["total"] == 1
    archivo = result["archivos"][0]
    assert archivo["id"] == "8012"
    assert archivo["subgrupo"] is None
    assert archivo["formato"] == "DESCONOCIDO"
    assert archivo["titulo"] == "Indicadores ACTI 2021"


@pytest.mark.asyncio
async def test_get_categoria_archivos_nested_one_level_by_year(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    result = await client.get_biblioteca_categoria_archivos("PAC SENESCYT 2025")

    assert result["total"] == 1
    archivo = result["archivos"][0]
    assert archivo["subgrupo"] == "Enero 2025"
    assert archivo["titulo"] == "PAC Enero 2025"


@pytest.mark.asyncio
async def test_get_categoria_archivos_nested_three_levels_collapses_to_innermost(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    result = await client.get_biblioteca_categoria_archivos("Normativa")

    assert result["total"] == 1
    archivo = result["archivos"][0]
    # Three levels deep (Normativa > Reglamento... > a. Documento inicial);
    # subgrupo is only the nearest header, not a full breadcrumb — see the
    # module docstring.
    assert archivo["subgrupo"] == "a. Documento inicial"
    assert archivo["titulo"] == "Reglamento de Registro de Títulos"


@pytest.mark.asyncio
async def test_get_categoria_archivos_duplicate_id_across_categories_kept_in_both(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    acti = await client.get_biblioteca_categoria_archivos("Indicadores ACTI")
    acuerdos = await client.get_biblioteca_categoria_archivos("Acuerdos")

    # id 8012 appears in both categories on the real page — the source
    # filing the same document under two categories, not a parsing
    # artifact — so both listings are kept rather than deduped away.
    assert acti["archivos"][0]["id"] == "8012"
    assert acuerdos["archivos"][0]["id"] == "8012"


@pytest.mark.asyncio
async def test_get_categoria_archivos_empty_category(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    result = await client.get_biblioteca_categoria_archivos("Mecanismo de Participación Ciudadana")

    assert result["total"] == 0
    assert result["archivos"] == []


@pytest.mark.asyncio
async def test_get_categoria_archivos_unknown_raises(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    with pytest.raises(ValueError):
        await client.get_biblioteca_categoria_archivos("no-existe")


@pytest.mark.asyncio
async def test_empty_scrape_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_EMPTY_HTML)
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    first = await client.list_biblioteca_categorias()
    assert first["total"] == 0

    second = await client.list_biblioteca_categorias()
    assert second["total"] == 5

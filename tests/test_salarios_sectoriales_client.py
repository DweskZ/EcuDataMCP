import pytest

from helpers import salarios_sectoriales_client as ssc

# A trimmed excerpt reproducing the real page's anchor shape, mixing in the
# confirmed "Salarios Mínimos Sectoriales" entries for several years with
# real noise that must NOT match: a "Sectorial" plan (no "salari"), a
# "Salario Básico Unificado" agreement (no "sectorial"), and a "comisiones
# sectoriales" reform (has "sectorial" but not about wages at all).
_PAGE_HTML = """
<html><body>
<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=5249&amp;force=0" title="Ver Plan Sectorial del Trabajo 2025&#8211;2029" target="_blank" class="ver">ver</a>
<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=5249&amp;force=1" title="Descargar Plan Sectorial del Trabajo 2025&#8211;2029">desc</a>

<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=3478&amp;force=0" title="Ver  ACUERDO MINISTERIAL Nro. MDT-2024-300 FIJAR EL SALARIO B&Aacute;SICO UNIFICADO DEL TRABAJADOR EN GENERAL PARA EL A&Ntilde;O 2025" target="_blank" class="ver">ver</a>

<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=1900&amp;force=0" title="Ver 2023 - Acuerdo Ministerial Nro. MDT-2023-172, reformar el Acuerdo Ministerial Nro. MDT-2020-023 mediante el cual, se expidi&oacute; la norma para el fortalecimiento y optimizaci&oacute;n de comisiones sectoriales" target="_blank" class="ver">ver</a>

<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=3479&amp;force=0" title="Ver FIJAR LOS SUELDOS Y SALARIOS M&Iacute;NIMOS SECTORIALES Y LAS TARIFAS PARA EL SECTOR PRIVADO POR RAMAS DE ACTIVIDAD QUE ABARCAN LAS DIFERENTES COMISIONES SECTORIALES - ACUERDO MINISTERIAL Nro. MDT-2024-301" target="_blank" class="ver">ver</a>
<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=3479&amp;force=1" title="Descargar FIJAR LOS SUELDOS Y SALARIOS M&Iacute;NIMOS SECTORIALES Y LAS TARIFAS PARA EL SECTOR PRIVADO POR RAMAS DE ACTIVIDAD QUE ABARCAN LAS DIFERENTES COMISIONES SECTORIALES - ACUERDO MINISTERIAL Nro. MDT-2024-301">desc</a>

<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=3473&amp;force=0" title="Ver Tabla de Salarios M&iacute;nimos Sectoriales 2025" target="_blank" class="ver">ver</a>
<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=3474&amp;force=0" title="Ver Salarios M&iacute;nimos Sectoriales 2025" target="_blank" class="ver">ver</a>

<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=1575&amp;force=0" title="Ver Tabla de Salarios M&iacute;nimos Sectoriales 2024" target="_blank" class="ver">ver</a>
<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=1576&amp;force=0" title="Ver Salarios M&iacute;nimos Sectoriales 2024" target="_blank" class="ver">ver</a>

<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=1567&amp;force=0" title="Ver Salarios M&iacute;nimos Sectoriales 2021" target="_blank" class="ver">ver</a>

<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=1564&amp;force=0" title="Ver Tabla Salarios M&iacute;nimos Sectoriales 2020" target="_blank" class="ver">ver</a>
<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=1565&amp;force=0" title="Ver Salarios M&iacute;nimos Sectoriales 2020" target="_blank" class="ver">ver</a>
<a href="https://www.trabajo.gob.ec/wp-content/plugins/download-monitor/download.php?id=1565&amp;force=0" title="Ver Salarios M&iacute;nimos Sectoriales 2020" target="_blank" class="ver">ver (duplicado)</a>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    ssc._entries_cache.clear()
    yield
    ssc._entries_cache.clear()


@pytest.mark.asyncio
async def test_search_lists_only_sectoral_wage_entries(httpx_mock):
    httpx_mock.add_response(url=ssc._PAGE_URL, html=_PAGE_HTML)

    result = await ssc.search_tablas_sectoriales()

    # 8 real entries: id=3479, 3473, 3474, 1575, 1576, 1567, 1564, 1565
    # (the id=1565 duplicate href is deduped; the plan/SBU/comisiones noise
    # entries are excluded).
    assert result["total_en_biblioteca"] == 8
    assert result["total"] == 8
    ids = {t["id"] for t in result["tablas"]}
    assert ids == {"3479", "3473", "3474", "1575", "1576", "1567", "1564", "1565"}


@pytest.mark.asyncio
async def test_search_excludes_plan_sbu_and_comisiones_noise(httpx_mock):
    httpx_mock.add_response(url=ssc._PAGE_URL, html=_PAGE_HTML)

    result = await ssc.search_tablas_sectoriales()

    ids = {t["id"] for t in result["tablas"]}
    assert "5249" not in ids  # Plan Sectorial (no "salari")
    assert "3478" not in ids  # Salario Básico Unificado (no "sectorial")
    assert "1900" not in ids  # comisiones sectoriales reform (not wages)


@pytest.mark.asyncio
async def test_search_extracts_year_and_unescapes_title(httpx_mock):
    httpx_mock.add_response(url=ssc._PAGE_URL, html=_PAGE_HTML)

    result = await ssc.search_tablas_sectoriales()

    by_id = {t["id"]: t for t in result["tablas"]}
    assert by_id["3473"]["anio"] == 2025
    assert by_id["3473"]["titulo"] == "Tabla de Salarios Mínimos Sectoriales 2025"
    assert by_id["1564"]["anio"] == 2020


@pytest.mark.asyncio
async def test_search_filters_by_anio(httpx_mock):
    httpx_mock.add_response(url=ssc._PAGE_URL, html=_PAGE_HTML)

    result = await ssc.search_tablas_sectoriales(anio=2025)

    # id=3479's title only prints "MDT-2024-301" (the acuerdo's signing
    # year), so it's tagged anio=2024, not 2025 -- exactly the "signed the
    # year before it applies" caveat documented in the module docstring.
    assert result["total"] == 2
    assert result["total_en_biblioteca"] == 8
    assert {t["id"] for t in result["tablas"]} == {"3473", "3474"}


@pytest.mark.asyncio
async def test_search_tags_acuerdo_by_its_signing_year(httpx_mock):
    httpx_mock.add_response(url=ssc._PAGE_URL, html=_PAGE_HTML)

    result = await ssc.search_tablas_sectoriales(anio=2024)

    ids = {t["id"] for t in result["tablas"]}
    assert {"3479", "1575", "1576"} <= ids


@pytest.mark.asyncio
async def test_search_filters_to_no_results_for_2026(httpx_mock):
    httpx_mock.add_response(url=ssc._PAGE_URL, html=_PAGE_HTML)

    result = await ssc.search_tablas_sectoriales(anio=2026)

    assert result["total"] == 0
    assert "2026" in result["nota"]


@pytest.mark.asyncio
async def test_view_and_download_urls_differ_only_by_force_flag(httpx_mock):
    httpx_mock.add_response(url=ssc._PAGE_URL, html=_PAGE_HTML)

    result = await ssc.search_tablas_sectoriales(anio=2025)

    entry = next(t for t in result["tablas"] if t["id"] == "3473")
    assert entry["url_ver"].endswith("id=3473&force=0")
    assert entry["url_descarga"].endswith("id=3473&force=1")


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=ssc._PAGE_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=ssc._PAGE_URL, html=_PAGE_HTML)

    first = await ssc.search_tablas_sectoriales()
    assert first["total_en_biblioteca"] == 0

    second = await ssc.search_tablas_sectoriales()
    assert second["total_en_biblioteca"] == 8

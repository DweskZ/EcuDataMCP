import pytest

from helpers import mef_fiscal_client

# Trimmed but structurally faithful excerpt of the real
# https://www.economicoproductivo.gob.ec/estadistica-nueva-metodologia-2017-2022/
# markup (confirmed live 2026-09-02): direct XLSX links under
# /wp-content/uploads/<year>/<month>/..., on either the old finanzas.gob.ec
# host or the current economicoproductivo.gob.ec one, with a minority
# nested under an extra .../uploads/downloads/<year>/<month>/ segment.
_MEF_HTML = """
<html><body>
<div class="entry-content">
<a href="https://www.finanzas.gob.ec/wp-content/uploads/2026/06/6.Operaciones-de-Ingresos-y-Gastos-SPNF-2013-2026.xlsx">Descargar</a>
<a href="https://www.finanzas.gob.ec/wp-content/uploads/2026/06/6.Operaciones_de_Activos_Financieros_y_Pasivos_SPNF_2013-2026.xlsx">Descargar</a>
<a href="https://www.economicoproductivo.gob.ec/wp-content/uploads/2026/09/202605-Financiamiento-SPNF-y-subsectores-BLL.xlsx">Descargar</a>
<a href="https://www.finanzas.gob.ec/wp-content/uploads/downloads/2025/02/1.BAJO-LA-LINEA_SPNF-GG_2013-2023_31-01-2025-1.xlsx">Descargar</a>
<a href="https://www.finanzas.gob.ec/wp-content/uploads/2026/06/6.Operaciones-de-Ingresos-y-Gastos-SPNF-2013-2026.xlsx">Descargar (duplicado)</a>
</div>
</body></html>
"""

# Trimmed but structurally faithful excerpt of the real
# https://www.aduana.gob.ec/de-interes/tributos-recaudados/ markup (same
# download-monitor accordion pattern as helpers/cnig_client.py) confirmed
# live 2026-09-02, including the real "Advaalorem" typo on one file and one
# "OTROS TRIBUTOS" entry with no year in its label.
_SENAE_HTML = """
<html><body>
<div class="el-item">
<span class="titulo">ADVALOREM 2020</span>
<a href="https://www.aduana.gob.ec/wp-content/plugins/download-monitor/download.php?id=2905&force=0" title="Ver ADVALOREM 2020" target="_blank" class="ver">ver</a>
<a href="https://www.aduana.gob.ec/wp-content/plugins/download-monitor/download.php?id=2905&force=1" title="Descargar ADVALOREM 2020">descarga</a>
</div>
<div class="el-item">
<span class="titulo">Advaalorem-2016.xlsx</span>
<a href="https://www.aduana.gob.ec/wp-content/plugins/download-monitor/download.php?id=1319&force=0" title="Ver Advaalorem-2016.xlsx" target="_blank" class="ver">ver</a>
<a href="https://www.aduana.gob.ec/wp-content/plugins/download-monitor/download.php?id=1319&force=1" title="Descargar Advaalorem-2016.xlsx">descarga</a>
</div>
<div class="el-item">
<span class="titulo">OTROS TRIBUTOS</span>
<a href="https://www.aduana.gob.ec/wp-content/plugins/download-monitor/download.php?id=666&force=0" title="Ver OTROS TRIBUTOS" target="_blank" class="ver">ver</a>
<a href="https://www.aduana.gob.ec/wp-content/plugins/download-monitor/download.php?id=666&force=1" title="Descargar OTROS TRIBUTOS">descarga</a>
</div>
<div class="el-item">
<span class="titulo">TOTALES 2020</span>
<a href="https://www.aduana.gob.ec/wp-content/plugins/download-monitor/download.php?id=2542&force=0" title="Ver TOTALES 2020" target="_blank" class="ver">ver</a>
<a href="https://www.aduana.gob.ec/wp-content/plugins/download-monitor/download.php?id=2542&force=1" title="Descargar TOTALES 2020">descarga</a>
</div>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    mef_fiscal_client._mef_cache.clear()
    mef_fiscal_client._senae_cache.clear()
    yield
    mef_fiscal_client._mef_cache.clear()
    mef_fiscal_client._senae_cache.clear()


@pytest.mark.asyncio
async def test_search_operaciones_spnf_lists_all_files(httpx_mock):
    httpx_mock.add_response(url=mef_fiscal_client._MEF_PAGE_URL, html=_MEF_HTML)

    result = await mef_fiscal_client.search_operaciones_spnf()

    # The duplicated href is deduped.
    assert result["total_en_pagina"] == 4
    assert result["total"] == 4
    assert result["source"].startswith("Ministerio de Economía y Finanzas")
    labels = {f["label"]: f for f in result["archivos"]}
    assert "6.Operaciones de Ingresos y Gastos SPNF 2013 2026" in labels
    entry = labels["6.Operaciones de Ingresos y Gastos SPNF 2013 2026"]
    assert entry["format"] == "XLSX"
    assert entry["carpeta_publicacion"] == "2026-06"
    # The extra uploads/downloads/<year>/<month> nesting is still matched.
    assert "1.BAJO LA LINEA SPNF GG 2013 2023 31 01 2025 1" in labels
    assert labels["1.BAJO LA LINEA SPNF GG 2013 2023 31 01 2025 1"][
        "carpeta_publicacion"
    ] == "2025-02"


@pytest.mark.asyncio
async def test_search_operaciones_spnf_sorts_newest_publication_first(httpx_mock):
    httpx_mock.add_response(url=mef_fiscal_client._MEF_PAGE_URL, html=_MEF_HTML)

    result = await mef_fiscal_client.search_operaciones_spnf()

    carpetas = [f["carpeta_publicacion"] for f in result["archivos"]]
    assert carpetas == sorted(carpetas, reverse=True)
    assert carpetas[0] == "2026-09"


@pytest.mark.asyncio
async def test_search_operaciones_spnf_filters_by_query(httpx_mock):
    httpx_mock.add_response(url=mef_fiscal_client._MEF_PAGE_URL, html=_MEF_HTML)

    result = await mef_fiscal_client.search_operaciones_spnf(query="financiamiento")

    assert result["total"] == 1
    assert result["archivos"][0]["url"].endswith(
        "202605-Financiamiento-SPNF-y-subsectores-BLL.xlsx"
    )


@pytest.mark.asyncio
async def test_search_operaciones_spnf_filters_by_carpeta_publicacion(httpx_mock):
    httpx_mock.add_response(url=mef_fiscal_client._MEF_PAGE_URL, html=_MEF_HTML)

    result = await mef_fiscal_client.search_operaciones_spnf(query="2025-02")

    assert result["total"] == 1
    assert "BAJO LA LINEA" in result["archivos"][0]["label"]


@pytest.mark.asyncio
async def test_search_senae_tributos_lists_all_files(httpx_mock):
    httpx_mock.add_response(url=mef_fiscal_client._SENAE_PAGE_URL, html=_SENAE_HTML)

    result = await mef_fiscal_client.search_senae_tributos()

    assert result["total_en_pagina"] == 4
    assert result["total"] == 4
    assert result["source"].startswith("SENAE")
    labels = {f["label"]: f for f in result["archivos"]}
    assert labels["ADVALOREM 2020"]["categoria"] == "ADVALOREM"
    assert labels["ADVALOREM 2020"]["anio"] == 2020
    assert labels["ADVALOREM 2020"]["format"] == "XLSX"
    # The real typo ("Advaalorem") is still categorized as ADVALOREM.
    assert labels["Advaalorem 2016"]["categoria"] == "ADVALOREM"
    assert labels["Advaalorem 2016"]["anio"] == 2016
    # An entry with no year in its label gets anio=None, not a crash.
    assert labels["OTROS TRIBUTOS"]["categoria"] == "OTROS TRIBUTOS"
    assert labels["OTROS TRIBUTOS"]["anio"] is None
    assert labels["TOTALES 2020"]["categoria"] == "TOTALES"


@pytest.mark.asyncio
async def test_search_senae_tributos_filters_by_categoria(httpx_mock):
    httpx_mock.add_response(url=mef_fiscal_client._SENAE_PAGE_URL, html=_SENAE_HTML)

    result = await mef_fiscal_client.search_senae_tributos(query="advalorem")

    assert result["total"] == 2
    labels = {f["label"] for f in result["archivos"]}
    assert labels == {"ADVALOREM 2020", "Advaalorem 2016"}


@pytest.mark.asyncio
async def test_search_senae_tributos_filters_by_label_query(httpx_mock):
    httpx_mock.add_response(url=mef_fiscal_client._SENAE_PAGE_URL, html=_SENAE_HTML)

    result = await mef_fiscal_client.search_senae_tributos(query="totales")

    assert result["total"] == 1
    assert result["archivos"][0]["id"] == "2542"


@pytest.mark.asyncio
async def test_mef_and_senae_caches_are_independent(httpx_mock):
    httpx_mock.add_response(url=mef_fiscal_client._MEF_PAGE_URL, html=_MEF_HTML)
    httpx_mock.add_response(url=mef_fiscal_client._SENAE_PAGE_URL, html=_SENAE_HTML)

    mef_result = await mef_fiscal_client.search_operaciones_spnf()
    senae_result = await mef_fiscal_client.search_senae_tributos()

    assert mef_result["total_en_pagina"] == 4
    assert senae_result["total_en_pagina"] == 4


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=mef_fiscal_client._MEF_PAGE_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=mef_fiscal_client._MEF_PAGE_URL, html=_MEF_HTML)

    first = await mef_fiscal_client.search_operaciones_spnf()
    assert first["total_en_pagina"] == 0

    second = await mef_fiscal_client.search_operaciones_spnf()
    assert second["total_en_pagina"] == 4

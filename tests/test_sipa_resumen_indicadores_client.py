import asyncio

import pytest

from helpers import sipa_resumen_indicadores_client as client

# Trimmed but structurally real markup, based on the live 2026 page
# (sipa.agricultura.gob.ec/index.php/resumen-de-indicadores/2026) — only 4
# months published at verification time, plus the "Año 2018 / ... / Año
# 2026" nav paragraph.
_HTML_2026 = """
<html><body>
<div class="uk-margin">
    <p style="text-align: center;"><strong><a href="/index.php/resumen-de-indicadores">Año 2018</a> / <a href="/index.php/resumen-de-indicadores/2019">Año 2019</a> / <a href="/index.php/resumen-de-indicadores/2020">Año 2020</a> / <a href="/index.php/resumen-de-indicadores/2021">Año 2021</a> / <a  href="/index.php/resumen-de-indicadores/2022">Año 2022</a> / <a  href="/index.php/resumen-de-indicadores/2023">Año 2023</a> / <a  href="/index.php/resumen-de-indicadores/2024">Año 2024</a>
    / <a  href="/index.php/resumen-de-indicadores/2025">Año 2025</a>
    / <a  href="/index.php/resumen-de-indicadores/2026">Año 2026</a>
    </strong></p>
</div>
<div uk-grid>
    <div>
<div class="el-item uk-panel">
<div class="el-content uk-margin"><p><a href="/descargas/resumen-indicadores/2026/indicadores_enero_2026.pdf" target="_blank" rel="noopener noreferrer">Enero</a></p>
<p> </p></div>
</div>
</div>
    <div>
<div class="el-item uk-panel">
<div class="el-content uk-margin"><p><a href="/descargas/resumen-indicadores/2026/indicadores_febrero_2026.pdf" target="_blank" rel="noopener noreferrer">Febrero</a></p>
<p> </p></div>
</div>
</div>
    <div>
<div class="el-item uk-panel">
<div class="el-content uk-margin"><p><a href="/descargas/resumen-indicadores/2026/indicadores_marzo_2026.pdf" target="_blank" rel="noopener noreferrer">Marzo</a></p>
<p> </p></div>
</div>
</div>
    <div>
<div class="el-item uk-panel">
<div class="el-content uk-margin"><p><a href="/descargas/resumen-indicadores/2026/indicadores_abril_2026.pdf" target="_blank" rel="noopener noreferrer">Abril</a></p>
<p> </p></div>
</div>
</div>
</div>
<div><p></p><iframe src="https://online.fliphtml5.com/ijia/uhcj/" width="100%" height="500px" frameborder="0" allowfullscreen="allowfullscreen"></iframe></div>
</body></html>
"""

# Trimmed real markup for the 2018 page (bare URL, no /<year> suffix) — a
# different filename convention (indicadores-<mm>-18.pdf, no year
# subfolder) and, at verification time, a nav paragraph that had NOT been
# updated to include "Año 2026" — confirmed live, not a made-up edge case.
_HTML_2018 = """
<html><body>
<div class="uk-margin">
    <p style="text-align: center;"><strong><a href="/index.php/resumen-de-indicadores">Año 2018</a> / <a href="/index.php/resumen-de-indicadores/2019">Año 2019</a> / <a href="/index.php/resumen-de-indicadores/2020">Año 2020</a> / <a href="/index.php/resumen-de-indicadores/2021">Año 2021</a> / <a href="/index.php/resumen-de-indicadores/2022">Año 2022</a> / <a href="/index.php/resumen-de-indicadores/2023">Año 2023</a> / <a href="/index.php/resumen-de-indicadores/2024">Año 2024</a> / <a href="/index.php/resumen-de-indicadores/2025">Año 2025</a> </strong></p>
</div>
<div uk-grid>
    <div>
<div class="el-item uk-panel">
<div class="el-content uk-margin"><p><a href="/descargas/resumen-indicadores/indicadores-01-18.pdf" target="_blank" rel="noopener noreferrer">Enero</a></p></div>
</div>
</div>
    <div>
<div class="el-item uk-panel">
<div class="el-content uk-margin"><p><a href="/descargas/resumen-indicadores/indicadores-02-18.pdf" target="_blank" rel="noopener noreferrer">Febrero</a></p></div>
</div>
</div>
</div>
</body></html>
"""

_HTML_EMPTY = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    client._page_cache.clear()
    yield
    client._page_cache.clear()


def test_year_url_uses_bare_path_for_2018_and_suffixed_for_later_years():
    assert client._year_url(2018) == "https://sipa.agricultura.gob.ec/index.php/resumen-de-indicadores"
    assert (
        client._year_url(2025)
        == "https://sipa.agricultura.gob.ec/index.php/resumen-de-indicadores/2025"
    )


@pytest.mark.asyncio
async def test_get_resumen_indicadores_2026(httpx_mock):
    httpx_mock.add_response(url=client._year_url(2026), html=_HTML_2026)

    result = await client.get_resumen_indicadores(2026)

    assert result["anio"] == 2026
    assert len(result["meses"]) == 4
    first = result["meses"][0]
    assert first["mes"] == "Enero"
    assert first["formato"] == "PDF"
    assert first["url"] == (
        "https://sipa.agricultura.gob.ec/descargas/resumen-indicadores/2026/"
        "indicadores_enero_2026.pdf"
    )
    assert [m["mes"] for m in result["meses"]] == ["Enero", "Febrero", "Marzo", "Abril"]
    # Year nav is picked up even though it wasn't asked for explicitly.
    assert result["anios_disponibles"] == [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]


@pytest.mark.asyncio
async def test_get_resumen_indicadores_2018_uses_legacy_filename_pattern(httpx_mock):
    httpx_mock.add_response(url=client._year_url(2018), html=_HTML_2018)

    result = await client.get_resumen_indicadores(2018)

    assert result["anio"] == 2018
    assert len(result["meses"]) == 2
    assert result["meses"][0]["url"] == (
        "https://sipa.agricultura.gob.ec/descargas/resumen-indicadores/indicadores-01-18.pdf"
    )
    # This page's own nav paragraph lags behind — it does not mention 2026,
    # confirming anios_disponibles reflects what's actually on the page
    # rather than an authoritative, always-current index.
    assert 2026 not in result["anios_disponibles"]
    assert result["anios_disponibles"] == [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]


@pytest.mark.asyncio
async def test_get_resumen_indicadores_rejects_year_before_minimo():
    with pytest.raises(ValueError, match="no soportado"):
        await client.get_resumen_indicadores(2017)


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=client._year_url(2026), html=_HTML_EMPTY)
    httpx_mock.add_response(url=client._year_url(2026), html=_HTML_2026)

    first = await client.get_resumen_indicadores(2026)
    assert first["meses"] == []

    second = await client.get_resumen_indicadores(2026)
    assert len(second["meses"]) == 4


@pytest.mark.asyncio
async def test_concurrent_calls_for_same_uncached_year_fetch_only_once(httpx_mock):
    httpx_mock.add_response(url=client._year_url(2026), html=_HTML_2026)

    results = await asyncio.gather(
        client.get_resumen_indicadores(2026),
        client.get_resumen_indicadores(2026),
    )

    assert all(len(r["meses"]) == 4 for r in results)
    # Only one response was registered above; a second real HTTP call would
    # raise inside httpx_mock, so reaching this point confirms dedup.
    assert len(httpx_mock.get_requests()) == 1

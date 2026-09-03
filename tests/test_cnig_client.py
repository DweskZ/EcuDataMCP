import pytest

from helpers import cnig_client

# Trimmed but structurally faithful excerpt of the real
# https://www.igualdadgenero.gob.ec/violencia/ markup (confirmed live
# 2026-09-02): each entry is a "li-gray1" accordion item whose "Descargar"
# link title carries the clean label used for matching/display.
_PAGE_HTML = """
<html><body>
<ul class="ul-downloads">
<li class="li-gray1" id="cat-2495" >
    <a style="display: block;"><span class="ico">+</span>Femicidios y Homicidios Intencionales de Mujeres</a>
    <ul><li class="li-gray4"><div><span class="titulo">FEMICIDIOS Y HOMICIDIOS INTENCIONALES DE MUJERES</span>
    <a href="https://www.igualdadgenero.gob.ec/wp-content/plugins/download-monitor/download.php?id=3137&force=0" title="Ver FEMICIDIOS Y HOMICIDIOS INTENCIONALES DE MUJERES" target="_blank" class="ver">ver</a>
    <a href="https://www.igualdadgenero.gob.ec/wp-content/plugins/download-monitor/download.php?id=3137&force=1" title="Descargar FEMICIDIOS Y HOMICIDIOS INTENCIONALES DE MUJERES">descarga</a>
    </div></li></ul>
</li>
<li class="li-gray1" id="cat-2031" >
    <a style="display: block;"><span class="ico">+</span>Violencia de g&eacute;nero contra las mujeres a lo largo de la vida</a>
    <ul><li class="li-gray4"><div><span class="titulo">VIOLENCIA DE G&Eacute;NERO CONTRA LAS MUJERES A LO LARGO DE LA VIDA</span>
    <a href="https://www.igualdadgenero.gob.ec/wp-content/plugins/download-monitor/download.php?id=2315&force=0" title="Ver VIOLENCIA DE G&Eacute;NERO CONTRA LAS MUJERES A LO LARGO DE LA VIDA" target="_blank" class="ver">ver</a>
    <a href="https://www.igualdadgenero.gob.ec/wp-content/plugins/download-monitor/download.php?id=2315&force=1" title="Descargar VIOLENCIA DE G&Eacute;NERO CONTRA LAS MUJERES A LO LARGO DE LA VIDA">descarga</a>
    </div></li></ul>
</li>
<li class="li-gray1" id="cat-2969" >
    <a style="display: block;"><span class="ico">+</span>Numero de victimas de femicidio y homicidios segun relacion con victimario</a>
    <ul><li class="li-gray4"><div><span class="titulo">NUMERO DE VICTIMAS DE FEMICIDIO Y HOMICIDIOS INTERNACIONALES SEGUN RELACION CON EL PRESUNTO VICTIMARIO</span>
    <a href="https://www.igualdadgenero.gob.ec/wp-content/plugins/download-monitor/download.php?id=2969&force=0" title="Ver NUMERO DE VICTIMAS DE FEMICIDIO Y HOMICIDIOS INTERNACIONALES SEGUN RELACION CON EL PRESUNTO VICTIMARIO" target="_blank" class="ver">ver</a>
    <a href="https://www.igualdadgenero.gob.ec/wp-content/plugins/download-monitor/download.php?id=2969&force=1" title="Descargar NUMERO DE VICTIMAS DE FEMICIDIO Y HOMICIDIOS INTERNACIONALES SEGUN RELACION CON EL PRESUNTO VICTIMARIO">descarga</a>
    </div></li></ul>
</li>
</ul>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    cnig_client._files_cache.clear()
    yield
    cnig_client._files_cache.clear()


@pytest.mark.asyncio
async def test_search_femicidios_lists_all_entries(httpx_mock):
    httpx_mock.add_response(url=cnig_client._PAGE_URL, html=_PAGE_HTML)

    result = await cnig_client.search_femicidios()

    assert result["total"] == 3
    assert result["total_en_pagina"] == 3
    assert result["source"].startswith("CNIG")
    labels = {f["label"]: f for f in result["archivos"]}
    assert "FEMICIDIOS Y HOMICIDIOS INTENCIONALES DE MUJERES" in labels
    entry = labels["FEMICIDIOS Y HOMICIDIOS INTENCIONALES DE MUJERES"]
    assert entry["id"] == "3137"
    assert entry["format"] == "PDF"
    assert entry["url"] == (
        "https://www.igualdadgenero.gob.ec/wp-content/plugins/download-monitor/"
        "download.php?id=3137&force=1"
    )


@pytest.mark.asyncio
async def test_search_femicidios_decodes_html_entities_in_label(httpx_mock):
    httpx_mock.add_response(url=cnig_client._PAGE_URL, html=_PAGE_HTML)

    result = await cnig_client.search_femicidios()

    labels = {f["label"] for f in result["archivos"]}
    assert "VIOLENCIA DE GÉNERO CONTRA LAS MUJERES A LO LARGO DE LA VIDA" in labels
    # No raw HTML entity should leak into a label.
    assert not any("&Eacute;" in label for label in labels)


@pytest.mark.asyncio
async def test_search_femicidios_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=cnig_client._PAGE_URL, html=_PAGE_HTML)

    result = await cnig_client.search_femicidios(query="genero")

    assert result["total"] == 1
    assert "GÉNERO" in result["archivos"][0]["label"]


@pytest.mark.asyncio
async def test_search_femicidios_filters_by_victimario_query(httpx_mock):
    httpx_mock.add_response(url=cnig_client._PAGE_URL, html=_PAGE_HTML)

    result = await cnig_client.search_femicidios(query="victimario")

    assert result["total"] == 1
    assert result["archivos"][0]["id"] == "2969"


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=cnig_client._PAGE_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=cnig_client._PAGE_URL, html=_PAGE_HTML)

    first = await cnig_client.search_femicidios()
    assert first["total_en_pagina"] == 0

    second = await cnig_client.search_femicidios()
    assert second["total_en_pagina"] == 3

import pytest

from helpers import minedec_client

# Trimmed from the real live markup (educacion.gob.ec/datos-abiertos-minedec/,
# confirmed 2026-09-03): file links are <a> tags wrapping icon <img>s with no
# usable link text, plus one unrelated file (Manual-MAIS-CE.pdf, a
# health-in-schools manual) reachable from the same nav that must NOT be
# picked up by the registry scrape.
_PAGE_HTML = """
<html><body>
<li><a href='https://educacion.gob.ec/wp-content/uploads/downloads/2019/02/Manual-MAIS-CE.pdf'>Manual MAIS-CE</a></li>
<div class="elementor-widget-container">
    <a href="https://educacion.gob.ec/wp-content/uploads/downloads/2026/04/1Registro-Administrativo-Historico_2009-202X-Inicio.xlsx" target="_blank">
        <img src="https://educacion.gob.ec/wp-content/uploads/2021/07/DA-inicio.png" alt="" />
    </a>
</div>
<div class="elementor-widget-container">
    <a href="https://educacion.gob.ec/wp-content/uploads/downloads/2026/04/2Registro-Administrativo-Historico_2009-2024-Fin.xlsx">
        <img src="https://educacion.gob.ec/wp-content/uploads/2021/07/DA-fin.png" alt="" />
    </a>
</div>
<div class="elementor-widget-container">
    <a href="https://educacion.gob.ec/wp-content/uploads/downloads/2026/04/3MINEDEC_Metadato_RegistroAdministrativo_2009_2025_Inicio.xlsx">
        <img src="https://educacion.gob.ec/wp-content/uploads/2021/07/DA-inicio.png" alt="" />
    </a>
</div>
<div class="elementor-widget-container">
    <a href="https://educacion.gob.ec/wp-content/uploads/downloads/2026/04/4MINEDUC_metadato_RegistroAdministrativo_2021-202Fin.xlsx">
        <img src="https://educacion.gob.ec/wp-content/uploads/2021/07/DA-fin.png" alt="" />
    </a>
</div>
<div class="elementor-widget-container">
    <a href="https://educacion.gob.ec/wp-content/uploads/downloads/2026/04/5Diccionario_Registro-Administrativo-Historico.xlsx">
        <img src="https://educacion.gob.ec/wp-content/uploads/2021/07/DA-diccionario.png" alt="" />
    </a>
</div>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    minedec_client._files_cache.clear()
    yield
    minedec_client._files_cache.clear()


@pytest.mark.asyncio
async def test_search_matricula_lists_all_files_excluding_unrelated_manual(httpx_mock):
    httpx_mock.add_response(url=minedec_client._PAGE_URL, html=_PAGE_HTML)

    result = await minedec_client.search_matricula()

    # 5 registry-related files; the unrelated Manual-MAIS-CE.pdf is excluded.
    assert result["total_en_pagina"] == 5
    assert result["total"] == 5
    urls = {f["url"] for f in result["archivos"]}
    assert not any("Manual-MAIS-CE" in u for u in urls)
    assert result["url_fuente"] == minedec_client._PAGE_URL


@pytest.mark.asyncio
async def test_search_matricula_classifies_tipo_and_periodo(httpx_mock):
    httpx_mock.add_response(url=minedec_client._PAGE_URL, html=_PAGE_HTML)

    result = await minedec_client.search_matricula()

    by_url = {f["url"]: f for f in result["archivos"]}

    registro_inicio = by_url[
        "https://educacion.gob.ec/wp-content/uploads/downloads/2026/04/"
        "1Registro-Administrativo-Historico_2009-202X-Inicio.xlsx"
    ]
    assert registro_inicio["tipo"] == "registro"
    assert registro_inicio["periodo"] == "inicio"
    assert registro_inicio["format"] == "XLSX"

    registro_fin = by_url[
        "https://educacion.gob.ec/wp-content/uploads/downloads/2026/04/"
        "2Registro-Administrativo-Historico_2009-2024-Fin.xlsx"
    ]
    assert registro_fin["tipo"] == "registro"
    assert registro_fin["periodo"] == "fin"

    metadato_inicio = by_url[
        "https://educacion.gob.ec/wp-content/uploads/downloads/2026/04/"
        "3MINEDEC_Metadato_RegistroAdministrativo_2009_2025_Inicio.xlsx"
    ]
    assert metadato_inicio["tipo"] == "metadato"
    assert metadato_inicio["periodo"] == "inicio"

    metadato_fin = by_url[
        "https://educacion.gob.ec/wp-content/uploads/downloads/2026/04/"
        "4MINEDUC_metadato_RegistroAdministrativo_2021-202Fin.xlsx"
    ]
    assert metadato_fin["tipo"] == "metadato"
    assert metadato_fin["periodo"] == "fin"

    diccionario = by_url[
        "https://educacion.gob.ec/wp-content/uploads/downloads/2026/04/"
        "5Diccionario_Registro-Administrativo-Historico.xlsx"
    ]
    assert diccionario["tipo"] == "diccionario"
    assert diccionario["periodo"] is None


@pytest.mark.asyncio
async def test_search_matricula_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=minedec_client._PAGE_URL, html=_PAGE_HTML)

    result = await minedec_client.search_matricula(query="diccionario")

    assert result["total"] == 1
    assert result["archivos"][0]["tipo"] == "diccionario"


@pytest.mark.asyncio
async def test_search_matricula_filters_by_periodo(httpx_mock):
    httpx_mock.add_response(url=minedec_client._PAGE_URL, html=_PAGE_HTML)

    result = await minedec_client.search_matricula(query="fin")

    periodos = {f["periodo"] for f in result["archivos"]}
    assert periodos == {"fin"}
    assert result["total"] == 2


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=minedec_client._PAGE_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(url=minedec_client._PAGE_URL, html=_PAGE_HTML)

    first = await minedec_client.search_matricula()
    assert first["total_en_pagina"] == 0

    second = await minedec_client.search_matricula()
    assert second["total_en_pagina"] == 5

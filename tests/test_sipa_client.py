import asyncio

import pytest

from helpers import sipa_client

_MODULE_HTML_TOLERANT = """
<html><body>
<div class="el-item">
    <h3 class="el-title uk-accordion-title">
        1. Precios productor        </h3>
    <div class="uk-accordion-content">
        <div class="uk-margin el-content">
            <p style="text-align: justify;">Archivo estadístico sobre precios mensuales.</p>
        </div>
        <p><a href="https://sipa.agricultura.gob.ec/descargas/base-estadistica/modulo_economico/precios-productor.xlsx" target="_blank" class="el-link uk-button">Descarga aquí</a></p>
    </div>
</div>
</body></html>
"""

_MODULE_HTML_UNKNOWN_ITEM = """
<html><body>
<div class="el-item">
    <h3 class="el-title uk-accordion-title">
        1. Valor agregado bruto agropecuario - PIB        </h3>
    <div class="uk-accordion-content">
        <div class="uk-margin el-content"><p>Archivo estadístico real.</p></div>
        <p><a href="https://sipa.agricultura.gob.ec/descargas/base-estadistica/modulo_economico/valor-agregado-bruto-agropecuario.xlsx" class="el-link uk-button">Descarga aquí</a></p>
    </div>
</div>
<div class="el-item">
    <div class="promo-banner">Este bloque no tiene título ni link reconocible.</div>
</div>
</body></html>
"""

_MODULE_HTML_EMPTY = """
<html><body><p>Sitio en mantenimiento.</p></body></html>
"""

_MODULE_HTML = """
<html><body>
<div id="page#20" uk-accordion>
    <div class="el-item">
        <h3 class="el-title uk-accordion-title">
            1. Valor agregado bruto agropecuario - PIB        </h3>
        <div class="uk-accordion-content">
            <div class="uk-margin el-content"><p style="text-align: justify;">Archivo estadístico sobre el Valor Agregado Bruto Agropecuario. Datos desde el año 2000.</p></div>
            <p><a href="https://sipa.agricultura.gob.ec/descargas/base-estadistica/modulo_economico/valor-agregado-bruto-agropecuario.xlsx" class="el-link uk-button uk-button-primary uk-button-small">Descarga aquí</a></p>
        </div>
    </div>
    <div class="el-item">
        <h3 class="el-title uk-accordion-title">
            2. Comercio exterior agropecuario y agroindustrial        </h3>
        <div class="uk-accordion-content">
            <div class="uk-margin el-content"><p style="text-align: justify;">Archivo estadístico sobre exportaciones, importaciones y balanza comercial. Datos desde el año 2000.</p></div>
            <p><a href="https://sipa.agricultura.gob.ec/descargas/base-estadistica/modulo_economico/comercio-exterior-agropecuario-agroindustrial.xlsx" class="el-link uk-button uk-button-primary uk-button-small">Descarga aquí</a></p>
        </div>
    </div>
    <div class="el-item">
        <h3 class="el-title uk-accordion-title">
            3. Censo Agropecuario 2000        </h3>
        <div class="uk-accordion-content">
            <p><a href="https://sipa.agricultura.gob.ec/descargas/base-estadistica/censos/censo_agropecuario_2000.xls" class="el-link uk-button uk-button-primary uk-button-small">Descarga aquí</a></p>
        </div>
    </div>
</div>
</body></html>
"""


@pytest.fixture(autouse=True)
def clear_cache():
    sipa_client._files_cache.clear()
    yield
    sipa_client._files_cache.clear()


def test_list_modulos_returns_four_fixed_modules():
    modulos = sipa_client.list_modulos()

    assert len(modulos) == 4
    keys = {m["modulo"] for m in modulos}
    assert keys == {"economico", "productivo", "social", "censos"}
    # Defensive copy, not the live list.
    modulos[0]["modulo"] = "mutated"
    assert sipa_client.list_modulos()[0]["modulo"] != "mutated"


@pytest.mark.asyncio
async def test_get_modulo_archivos(httpx_mock):
    url = sipa_client._MODULOS_BY_KEY["economico"]["url"]
    httpx_mock.add_response(url=url, html=_MODULE_HTML)

    result = await sipa_client.get_modulo_archivos("economico")

    assert result["modulo"] == "economico"
    assert len(result["archivos"]) == 3

    first = result["archivos"][0]
    assert first["numero"] == 1
    assert first["titulo"] == "Valor agregado bruto agropecuario - PIB"
    assert "Datos desde el año 2000" in first["descripcion"]
    assert first["formato"] == "XLSX"
    assert first["url"].endswith("valor-agregado-bruto-agropecuario.xlsx")

    second = result["archivos"][1]
    assert second["numero"] == 2
    assert second["titulo"] == "Comercio exterior agropecuario y agroindustrial"

    # censos-style items have no description paragraph at all — must not
    # be silently dropped, and descripcion should fall back to "".
    third = result["archivos"][2]
    assert third["numero"] == 3
    assert third["titulo"] == "Censo Agropecuario 2000"
    assert third["descripcion"] == ""
    assert third["formato"] == "XLS"


@pytest.mark.asyncio
async def test_get_modulo_archivos_rejects_unknown_modulo():
    with pytest.raises(ValueError, match="no reconocido"):
        await sipa_client.get_modulo_archivos("no-existe")


def test_description_regex_tolerates_whitespace_between_div_and_p():
    html = """
    <div class="el-item">
        <h3 class="el-title uk-accordion-title">
            1. Precios productor        </h3>
        <div class="uk-accordion-content">
            <div class="uk-margin el-content">
                <p style="text-align: justify;">Descripción con salto de línea antes del párrafo.</p>
            </div>
            <p><a href="https://sipa.agricultura.gob.ec/descargas/base-estadistica/modulo_economico/precios-productor.xlsx" class="el-link uk-button">Descarga aquí</a></p>
        </div>
    </div>
    """
    archivos = sipa_client._parse_archivos(html, "economico")

    assert len(archivos) == 1
    assert "salto de línea" in archivos[0]["descripcion"]


@pytest.mark.asyncio
async def test_link_regex_tolerates_extra_attribute_between_href_and_class(httpx_mock):
    # A routine CMS re-save (e.g. adding target="_blank") must not make the
    # item vanish — the link regex should not require exact adjacency.
    url = sipa_client._MODULOS_BY_KEY["economico"]["url"]
    httpx_mock.add_response(url=url, html=_MODULE_HTML_TOLERANT)

    result = await sipa_client.get_modulo_archivos("economico")

    assert len(result["archivos"]) == 1
    assert result["archivos"][0]["url"].endswith("precios-productor.xlsx")


@pytest.mark.asyncio
async def test_unmatched_item_is_logged_and_skipped_without_dropping_others(httpx_mock, caplog):
    url = sipa_client._MODULOS_BY_KEY["economico"]["url"]
    httpx_mock.add_response(url=url, html=_MODULE_HTML_UNKNOWN_ITEM)

    with caplog.at_level("WARNING"):
        result = await sipa_client.get_modulo_archivos("economico")

    # The real item is still returned...
    assert len(result["archivos"]) == 1
    assert result["archivos"][0]["titulo"] == "Valor agregado bruto agropecuario - PIB"
    # ...and the skipped one leaves a diagnostic trail instead of vanishing silently.
    assert any("no matcheó el patrón esperado" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_empty_parse_result_is_not_cached(httpx_mock):
    url = sipa_client._MODULOS_BY_KEY["economico"]["url"]
    httpx_mock.add_response(url=url, html=_MODULE_HTML_EMPTY)
    httpx_mock.add_response(url=url, html=_MODULE_HTML_TOLERANT)

    first = await sipa_client.get_modulo_archivos("economico")
    assert first["archivos"] == []

    # A second call must re-fetch rather than serve the cached empty result.
    second = await sipa_client.get_modulo_archivos("economico")
    assert len(second["archivos"]) == 1


@pytest.mark.asyncio
async def test_formato_falls_back_to_desconocido_for_extensionless_url():
    html = _MODULE_HTML_TOLERANT.replace(
        "precios-productor.xlsx", "precios-productor/descargar"
    )
    archivos = sipa_client._parse_archivos(html, "economico")

    assert archivos[0]["formato"] == "DESCONOCIDO"


@pytest.mark.asyncio
async def test_concurrent_calls_for_same_uncached_modulo_fetch_only_once(httpx_mock):
    url = sipa_client._MODULOS_BY_KEY["economico"]["url"]
    httpx_mock.add_response(url=url, html=_MODULE_HTML_TOLERANT)

    results = await asyncio.gather(
        sipa_client.get_modulo_archivos("economico"),
        sipa_client.get_modulo_archivos("economico"),
    )

    assert all(len(r["archivos"]) == 1 for r in results)
    # Only one response was registered above; a second real HTTP call would
    # raise inside httpx_mock, so reaching this point confirms dedup.
    assert len(httpx_mock.get_requests()) == 1

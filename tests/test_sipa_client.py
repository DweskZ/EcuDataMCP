import pytest

from helpers import sipa_client

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

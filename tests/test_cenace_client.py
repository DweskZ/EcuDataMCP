import pytest

from helpers import cenace_client as cenace

_RESUMEN_TEMPLATE = """
                <div class="resumen">
                    <div class="resumen-box total"><div>PRODUCCIÓN TOTAL</div><div>{total}</div></div>
                    <div class="resumen-box exportacion"><div>EXPORTACIÓN</div><div>0</div></div>
                    <div class="resumen-box importacion"><div>IMPORTACIÓN</div><div>4\xa0307</div></div>
                    <div class="resumen-box hidraulica"><div>HIDRÁULICA</div><div>70\xa0312</div></div>
                    <div class="resumen-box otra"><div>TÉRMICA</div><div>22\xa0431</div></div>
                    <div class="resumen-box noconvencional"><div>R. NO CONVENCIONAL</div><div>596</div></div>
                </div>
"""

_DEMANDA_RESUMEN = """
                <div class="resumen">
                    <div class="resumen-box total"><div>DEMANDA TOTAL</div><div>4\xa0049</div></div>
                    <div class="resumen-box anterior"><div>ANTERIOR</div><div>4\xa0227</div></div>
                    <div class="resumen-box exportacion"><div>DEMANDA CNEL</div><div>3\xa0031</div></div>
                    <div class="resumen-box hidraulica"><div>EMPRESAS ELÉCTRICAS</div><div>1\xa0018</div></div>
                </div>
"""

_SVG_TITLES = """
        <title>CNEL SANTA ELENA&#10;102 MW</title>
        <title>CNEL GUAYAQUIL&#10;1\xa0011 MW</title>
"""

_RESUMEN_TIEMPO_REAL = _RESUMEN_TEMPLATE.format(total="97\xa0995")
_RESUMEN_DIARIA = _RESUMEN_TEMPLATE.format(total="111\xa0868")
_RESUMEN_MENSUAL = _RESUMEN_TEMPLATE.format(total="2\xa0880\xa0652")
_RESUMEN_ANUAL = _RESUMEN_TEMPLATE.format(total="24\xa0482")

_PAGE = f"""<!doctype html><html><body>
<div class="tab-content active">
    <header><h2>PRODUCCIÓN EN TIEMPO REAL</h2></header>
    <div style="text-align: center;"><span>Domingo, 30 de agosto de 2026</span></div>
    <div class="dashboard"><div class="resumen-container"><h3>PRODUCCIÓN ENERGÉTICA (MWh)</h3>
    {_RESUMEN_TIEMPO_REAL}
    </div></div>
</div>
<div class="tab-content">
    <header><h2>DEMANDAS EMPRESAS ELÉCTRICAS DE DISTRIBUCIÓN</h2></header>
    <div style="text-align: center;"><span>Domingo, 30 de agosto de 2026</span></div>
    <div class="dashboard"><div class="resumen-container"><h3>DEMANDA (MW)</h3>
    {_DEMANDA_RESUMEN}
    </div>
    <svg>{_SVG_TITLES}</svg>
    </div>
</div>
<div class="tab-content">
    <header><h2>INFORMACIÓN OPERATIVA DIARIA</h2></header>
    <div style="text-align: center;"><span>Jueves, 27 de agosto de 2026</span></div>
    <div class="dashboard"><div class="resumen-container"><h3>PRODUCCIÓN ENERGÉTICA (MWh)</h3>
    {_RESUMEN_DIARIA}
    </div></div>
</div>
<div class="tab-content">
    <header><h2>INFORMACIÓN OPERATIVA MENSUAL</h2></header>
    <div style="text-align: center;"><span>Agosto de 2026 (hasta el día 27)</span></div>
    <div class="dashboard"><div class="resumen-container"><h3>PRODUCCIÓN ENERGÉTICA (MWh)</h3>
    {_RESUMEN_MENSUAL}
    </div></div>
</div>
<div class="tab-content">
    <header><h2>INFORMACIÓN OPERATIVA ANUAL</h2></header>
    <div style="text-align: center;"><span>2026 (hasta el día 27 de agosto)</span></div>
    <div class="dashboard"><div class="resumen-container"><h3>PRODUCCIÓN ENERGÉTICA (GWh)</h3>
    {_RESUMEN_ANUAL}
    </div></div>
</div>
</body></html>"""


@pytest.fixture(autouse=True)
def clear_cache():
    cenace._cache.clear()
    yield
    cenace._cache.clear()


def test_list_tableros_returns_fixed_set():
    assert cenace.list_tableros() == [
        "produccion_tiempo_real",
        "demanda_tiempo_real",
        "operativa_diaria",
        "acumulada_mensual",
        "acumulada_anual",
    ]


@pytest.mark.asyncio
async def test_get_tablero_rejects_unknown_name():
    with pytest.raises(ValueError, match="no reconocido"):
        await cenace.get_tablero("no-existe")


@pytest.mark.asyncio
async def test_get_tablero_parses_resumen_and_period(httpx_mock):
    httpx_mock.add_response(url=cenace._URL, text=_PAGE)

    result = await cenace.get_tablero("produccion_tiempo_real")

    assert result["titulo"] == "PRODUCCIÓN EN TIEMPO REAL"
    assert result["periodo"] == "Domingo, 30 de agosto de 2026"
    assert result["resumen"] == {
        "PRODUCCIÓN TOTAL": 97995,
        "EXPORTACIÓN": 0,
        "IMPORTACIÓN": 4307,
        "HIDRÁULICA": 70312,
        "TÉRMICA": 22431,
        "R. NO CONVENCIONAL": 596,
    }
    assert "por_distribuidora_mw" not in result


@pytest.mark.asyncio
async def test_get_tablero_demanda_includes_distribuidora_breakdown(httpx_mock):
    httpx_mock.add_response(url=cenace._URL, text=_PAGE)

    result = await cenace.get_tablero("demanda_tiempo_real")

    assert result["resumen"]["DEMANDA TOTAL"] == 4049
    assert result["resumen"]["DEMANDA CNEL"] == 3031
    assert result["por_distribuidora_mw"] == {
        "CNEL SANTA ELENA": 102,
        "CNEL GUAYAQUIL": 1011,
    }


@pytest.mark.asyncio
async def test_get_tablero_handles_thousands_separator_across_tabs(httpx_mock):
    httpx_mock.add_response(url=cenace._URL, text=_PAGE)

    mensual = await cenace.get_tablero("acumulada_mensual")

    assert mensual["resumen"]["PRODUCCIÓN TOTAL"] == 2880652
    assert mensual["periodo"] == "Agosto de 2026 (hasta el día 27)"


@pytest.mark.asyncio
async def test_get_tablero_caches_page_across_calls(httpx_mock):
    httpx_mock.add_response(url=cenace._URL, text=_PAGE)

    await cenace.get_tablero("produccion_tiempo_real")
    await cenace.get_tablero("acumulada_anual")

    assert len(httpx_mock.get_requests()) == 1

import pytest

from helpers import aviacion_client

# Trimmed real shapes confirmed live on www.ais.aviacioncivil.gob.ec
# (2026-09-02), captured with curl (no auth, no session cookie resubmitted).

_METAR_SEQM_HTML = """
<html><body>
<div class="left">
    <div class="taf">
        <div class="taf_h1">
            METAR del 03-09-2026 a las 01:00 UTC
        </div>
        <div class="taf_h3 codificacion">
            SEQM 030100Z 30004KT 9999 FEW030 17/08 Q1026 NOSIG RMK A3032=      </div>
        <div class="taf_p">Viento:  direcci&oacute;n 300 grados, velocidad  4 nudos</div>
    </div>
    <div class="taf">
        <div class="taf_h1">
            METAR del 03-09-2026 a las 00:00 UTC
        </div>
        <div class="taf_h3 codificacion">
            SEQM 030000Z 07003KT 9999 SCT050 16/09 Q1025 NOSIG RMK A3029=      </div>
    </div>
</div>
</body></html>
"""

_METAR_NOT_FOUND_HTML = """
<html><body>
<div class="left">
    <div class="informacion">
        No existe registro de METAR para el  aer&oacute;dromo ZZZZ(ZZZZ)
    </div>
</div>
</body></html>
"""

_NOTAM_SEQM_HTML = """
<html><body>
<div class="notam-categorias">
    <a href="/notam?designador=SEQM"> NOTAMs (2)</a>
</div>
<table class="metar" summary="Descripci&oacute;n de Informe Notam para  aer&amp;oacute;dromo Mariscal Sucre Intl.(SEQM)">
    <caption>Descripci&oacute;n de Informe NOTAM para aer&oacute;dromo Mariscal Sucre Intl.(SEQM)</caption>
    <thead><tr><th id="notam">NOTAM</th><th id="indice">&Iacute;ndice</th><th id="valor">Valor</th></tr></thead>
    <tbody>
        <tr><td class="glosa"></td><td class="glosa"></td><td class="glosa"></td></tr>
        <tr class="notam_raw">
            <td rowspan="15" headers="notam" class="codificacion">
                C1333/26 NOTAMN<br />
Q)SEFG/QWULW/IV/BO/AW/000/004/0007S07829W001<br />
A)SEQM B)2608211400 C)2611192100 EST<br />
E)FLT UA SECT PARQUE BICENTENARIO<br />
F)GND G)400FT AGL          </td>
            <td></td>
            <td></td>
        </tr>
        <tr>
            <td scope="row" id="fecha155931" headers="indice">Fecha mensaje</td>
            <td headers="fecha155931 valor">2026-08-20 20:32:00</td>
        </tr>
        <tr>
            <td scope="row" id="tipo155931" headers="indice">Tipo</td>
            <td headers="tipo155931 valor">N</td>
        </tr>
        <tr>
            <td scope="row" id="identificador_de_lugar155931" headers="indice">FIR</td>
            <td headers="identificador_de_lugar155931 valor">SEFG</td>
        </tr>
        <tr>
            <td scope="row" id="codigo155931" headers="indice">C&oacute;digo</td>
            <td headers="codigo155931 valor">WU / Se realizar&aacute; </td>
        </tr>
        <tr>
            <td scope="row" id="comienzo_validez155931" headers="indice">Comienzo validez</td>
            <td headers="comienzo_validez155931 valor">21/08/26 14:00</td>
        </tr>
        <tr>
            <td scope="row" id="termino_validez155931" headers="indice">T&eacute;rmino validez</td>
            <td headers="termino_validez155931 valor">19/11/26 21:00</td>
        </tr>
        <tr><td class="glosa"></td><td class="glosa"></td><td class="glosa"></td></tr>
        <tr class="notam_raw">
            <td rowspan="14" headers="notam" class="codificacion">
                A1784/26 NOTAMR A1142/26<br />
Q)SEFG/QPDAU/I/NBO/A/000/999/0007S07821W005<br />
A)SEQM B)2607231649 C)2610221800 EST<br />
E)ID 1F - ARNOK 4, ANBAL 3 - RWY 36 NOT AVBL          </td>
            <td></td>
            <td></td>
        </tr>
        <tr>
            <td scope="row" id="fecha155552" headers="indice">Fecha mensaje</td>
            <td headers="fecha155552 valor">2026-07-23 17:16:00</td>
        </tr>
        <tr>
            <td scope="row" id="tipo155552" headers="indice">Tipo</td>
            <td headers="tipo155552 valor">R</td>
        </tr>
    </tbody>
</table>
</body></html>
"""

_NOTAM_EMPTY_HTML = """
<html><body>
<div class="notam-categorias">
    <a href="/notam?designador=ZZZZ"> NOTAMs (0)</a>
</div>
<table class="metar">
    <thead><tr><th id="notam">NOTAM</th><th id="indice">&Iacute;ndice</th><th id="valor">Valor</th></tr></thead>
    <tbody>
    </tbody>
</table>
</body></html>
"""

_SIGMET_ACTIVE_HTML = """
<html><body>
<h1>SIGMET</h1>
<table class="metar">
    <thead>
        <tr><th id="indice">&Iacute;ndice</th><th id="valor">Valor</th><th id="sigmet">SIGMET/Mapa</th></tr>
    </thead>
    <tbody>
        <tr><td class="glosa"></td><td class="glosa"></td><td class="glosa"></td></tr>
        <tr class="sigmet_raw">
            <td scope="row" id="fecha36790" headers="indice">Fecha mensaje</td>
            <td headers="fecha36790 valor">2026-09-02 19:58:00</td>
            <td rowspan="13" headers="sigmet" style="width:300px" class="codificacion">
                WVEQ31 SEQU 021958<br />
SEFG SIGMET 4 VALID 021958/030158 SEGU-<br />
SEFG GUAYAQUIL FIR VA ERUPTION MT REVENTADOR PSN S0004 W07739<br />
VA CLD OBS AT 1920Z WI N0004 W07745 - S0004 W07738 SFC/FL150 MOV NW 10KT=          </td>
        </tr>
        <tr>
            <td scope="row" id="tipo36790" headers="indice">Tipo</td>
            <td headers="tipo36790 valor">
                Ceniza Volc&aacute;nica en la FIR del Ecuador</td>
        </tr>
        <tr>
            <td scope="row" id="pais36790" headers="indice">Pa&iacute;s</td>
            <td headers="pais36790 valor">
                Ecuador</td>
        </tr>
        <tr>
            <td scope="row" id="start36790" headers="indice">Desde</td>
            <td headers="start36790 valor">2026-09-02 19:58:00</td>
        </tr>
        <tr>
            <td scope="row" id="end36790" headers="indice">Hasta</td>
            <td headers="end36790 valor">2026-09-03 01:58:00</td>
        </tr>
    </tbody>
</table>
</body></html>
"""

_SIGMET_EMPTY_HTML = """
<html><body>
<h1>SIGMET</h1>
<table class="metar">
    <thead>
        <tr><th id="indice">&Iacute;ndice</th><th id="valor">Valor</th><th id="sigmet">SIGMET/Mapa</th></tr>
    </thead>
    <tbody>
    </tbody>
</table>
</body></html>
"""


@pytest.fixture(autouse=True)
def clear_cache():
    aviacion_client.clear_cache()
    yield
    aviacion_client.clear_cache()


# --- METAR -------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_metar_parses_reports(httpx_mock):
    httpx_mock.add_response(
        url="https://www.ais.aviacioncivil.gob.ec/metar/SEQM", html=_METAR_SEQM_HTML
    )

    result = await aviacion_client.get_metar("SEQM")

    assert result["designador"] == "SEQM"
    assert result["total"] == 2
    first = result["reportes"][0]
    assert first["tipo"] == "METAR"
    assert first["fecha_utc"] == "2026-09-03 01:00:00"
    assert first["raw"] == "SEQM 030100Z 30004KT 9999 FEW030 17/08 Q1026 NOSIG RMK A3032="
    assert result["reportes"][1]["fecha_utc"] == "2026-09-03 00:00:00"


@pytest.mark.asyncio
async def test_get_metar_normalizes_lowercase_designador(httpx_mock):
    httpx_mock.add_response(
        url="https://www.ais.aviacioncivil.gob.ec/metar/SEQM", html=_METAR_SEQM_HTML
    )

    result = await aviacion_client.get_metar("seqm")

    assert result["designador"] == "SEQM"
    assert result["total"] == 2


@pytest.mark.asyncio
async def test_get_metar_unknown_designador_returns_empty_not_error(httpx_mock):
    httpx_mock.add_response(
        url="https://www.ais.aviacioncivil.gob.ec/metar/ZZZZ", html=_METAR_NOT_FOUND_HTML
    )

    result = await aviacion_client.get_metar("ZZZZ")

    assert result["total"] == 0
    assert result["reportes"] == []


@pytest.mark.asyncio
async def test_get_metar_rejects_blank_designador():
    with pytest.raises(ValueError):
        await aviacion_client.get_metar("   ")


@pytest.mark.asyncio
async def test_get_metar_is_cached_across_calls(httpx_mock):
    httpx_mock.add_response(
        url="https://www.ais.aviacioncivil.gob.ec/metar/SEQM", html=_METAR_SEQM_HTML
    )

    first = await aviacion_client.get_metar("SEQM")
    second = await aviacion_client.get_metar("SEQM")

    assert first == second
    # Only one real HTTP request should have been made for the second call
    # to succeed without a matching mock registered twice.
    assert len(httpx_mock.get_requests()) == 1


# --- NOTAM ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_notam_parses_entries_and_metadata(httpx_mock):
    httpx_mock.add_response(
        url="https://www.ais.aviacioncivil.gob.ec/notam?designador=SEQM",
        html=_NOTAM_SEQM_HTML,
    )

    result = await aviacion_client.get_notam("SEQM")

    assert result["designador"] == "SEQM"
    assert result["aerodromo_nombre"] == "Mariscal Sucre Intl."
    assert result["aerodromo_icao"] == "SEQM"
    assert result["total"] == 2
    assert result["total_declarado"] == 2

    first = result["notams"][0]
    assert first["serie"] == "C1333/26"
    assert "Q)SEFG/QWULW/IV/BO/AW/000/004/0007S07829W001" in first["raw"]
    assert first["campos"]["Fecha mensaje"] == "2026-08-20 20:32:00"
    assert first["campos"]["Tipo"] == "N"
    assert first["campos"]["FIR"] == "SEFG"
    assert first["campos"]["Código"] == "WU / Se realizará"
    assert first["campos"]["Comienzo validez"] == "21/08/26 14:00"

    second = result["notams"][1]
    assert second["serie"] == "A1784/26"
    assert second["campos"]["Tipo"] == "R"


@pytest.mark.asyncio
async def test_get_notam_no_active_notams_returns_empty(httpx_mock):
    httpx_mock.add_response(
        url="https://www.ais.aviacioncivil.gob.ec/notam?designador=ZZZZ",
        html=_NOTAM_EMPTY_HTML,
    )

    result = await aviacion_client.get_notam("ZZZZ")

    assert result["total"] == 0
    assert result["notams"] == []
    assert result["total_declarado"] == 0


@pytest.mark.asyncio
async def test_get_notam_rejects_blank_designador():
    with pytest.raises(ValueError):
        await aviacion_client.get_notam("")


# --- SIGMET ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sigmet_parses_active_advisory(httpx_mock):
    httpx_mock.add_response(
        url="https://www.ais.aviacioncivil.gob.ec/sigmet", html=_SIGMET_ACTIVE_HTML
    )

    result = await aviacion_client.get_sigmet()

    assert result["total"] == 1
    sigmet = result["sigmets"][0]
    assert sigmet["raw"].startswith("WVEQ31 SEQU 021958")
    assert "VA ERUPTION MT REVENTADOR" in sigmet["raw"]
    assert sigmet["campos"]["Tipo"] == "Ceniza Volcánica en la FIR del Ecuador"
    assert sigmet["campos"]["País"] == "Ecuador"
    assert sigmet["campos"]["Desde"] == "2026-09-02 19:58:00"
    assert sigmet["campos"]["Hasta"] == "2026-09-03 01:58:00"


@pytest.mark.asyncio
async def test_get_sigmet_no_active_advisories(httpx_mock):
    httpx_mock.add_response(
        url="https://www.ais.aviacioncivil.gob.ec/sigmet", html=_SIGMET_EMPTY_HTML
    )

    result = await aviacion_client.get_sigmet()

    assert result["total"] == 0
    assert result["sigmets"] == []


@pytest.mark.asyncio
async def test_get_sigmet_is_cached_across_calls(httpx_mock):
    httpx_mock.add_response(
        url="https://www.ais.aviacioncivil.gob.ec/sigmet", html=_SIGMET_ACTIVE_HTML
    )

    first = await aviacion_client.get_sigmet()
    second = await aviacion_client.get_sigmet()

    assert first == second
    assert len(httpx_mock.get_requests()) == 1

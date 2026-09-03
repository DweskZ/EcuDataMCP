import asyncio

import pytest

from helpers import ineval_client

# Shaped after the real markup observed live 2026-09-02 on
# evaluaciones.evaluacion.gob.ec/BI/ser-estudiante-2/: a "Fichas
# metodológicas vigentes" standalone button, then a "Bases de datos"
# Bootstrap accordion with one <table class="table"> per "Año lectivo"
# panel (header row names the formats; SAV is empty for "Micro" in one
# panel, confirming empty cells are skipped rather than treated as errors).
_FAMILIA_HTML = """
<html><body>
<h3>Fichas metodológicas vigentes</h3>
<button type="button" class="btn btn-warning btn-lg"><a class="mint3"
        href="https://evaluaciones.evaluacion.gob.ec/BI/download/63392/"> <i class="fa-solid fa-arrow-down"></i>
        Descargar Fichas Metodológicas
    </a></button>
<h3>Bases de datos</h3>
<div class="accordion" id="accordionExample">
<div class="accordion-item">
    <h2 class="accordion-header" id="headingEleven">
        <button class="accordion-button collapsed" type="button">
            <strong> Año lectivo 2024-2025 </strong>
        </button>
    </h2>
    <div class="accordion-body">
        <div class="table-responsive">
            <table class="table">
                <tbody>
                    <tr>
                        <td>Archivo</td>
                        <td>Sintaxis</td>
                        <td>CSV</td>
                        <td>SAV</td>
                    </tr>
                    <tr>
                        <td>Micro</td>
                        <td><a href="https://evaluaciones.evaluacion.gob.ec/BI/download/76242/" target="_blank"><img src="icn.png"/></a></td>
                        <td><a href="https://evaluaciones.evaluacion.gob.ec/BI/download/76077/" target="_blank"><img src="icn.png"/></a></td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>Factores Asociados estudiantes</td>
                        <td></td>
                        <td><a href="https://evaluaciones.evaluacion.gob.ec/BI/download/76095/" target="_blank"><img src="icn.png"/></a></td>
                        <td><a href="https://evaluaciones.evaluacion.gob.ec/BI/download/76099/" target="_blank"><img src="icn.png"/></a></td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</div>
</div>
<h3>Información Estadística</h3>
<button type="button" class="btn btn-warning btn-lg">
    <a class="mint3" target="_blank" href="https://evaluaciones.evaluacion.gob.ec/BI/download/75662/"> <i
            class="fa-solid fa-arrow-down"></i>
        Descargar promedios históricos de indicadores principales
    </a> </button>
</body></html>
"""

# Shaped after llece-2/: bare <h2>Erce </h2>/<h2>Serce </h2> group headings
# (no class attribute) precede each round's own accordion -- distinct from
# every other <h2 class="gb-headline...">-style heading on these pages.
_LLECE_HTML = """
<html><body>
<h2 class="gb-headline gb-headline-3a6706b6 gb-headline-text">Datos por periodo</h2>
<h2>Erce </h2>
<div class="accordion" id="accordionExample">
<div class="accordion-item">
    <h2 class="accordion-header" id="heading0">
        <button class="accordion-button collapsed" type="button">
            <strong>Año 2019 </strong>
        </button>
    </h2>
    <div class="accordion-body"><div class="table-responsive">
        <table class="table">
            <tbody>
                <tr><td>Archivo</td><td>CSV</td><td>SAV</td></tr>
                <tr>
                    <td>Logros de aprendizaje</td>
                    <td><a href="https://evaluaciones.evaluacion.gob.ec/BI/download/5871/" target="_blank"><img src="icn.png"/></a></td>
                    <td><a href="https://evaluaciones.evaluacion.gob.ec/BI/download/5866/" target="_blank"><img src="icn.png"/></a></td>
                </tr>
            </tbody>
        </table>
    </div></div>
</div>
</div>
<h2>Serce </h2>
<div class="accordion" id="accordionExample2">
<div class="accordion-item">
    <h2 class="accordion-header" id="heading00">
        <button class="accordion-button collapsed" type="button">
            <strong>Año 2006</strong>
        </button>
    </h2>
    <div class="accordion-body"><div class="table-responsive">
        <table class="table">
            <tbody>
                <tr><td>Archivo</td><td>CSV</td></tr>
                <tr>
                    <td>Logros de aprendizaje</td>
                    <td><a href="https://evaluaciones.evaluacion.gob.ec/BI/download/3308/" target="_blank"><img src="icn.png"/></a></td>
                </tr>
            </tbody>
        </table>
    </div></div>
</div>
</div>
</body></html>
"""

# Shaped after the real gotcha found live on ser-maestro-2/: a stale,
# superseded <tr> of download links sits inside an HTML comment right
# beside the live row, both shaped identically.
_COMMENTED_ROW_HTML = """
<html><body>
<div class="accordion-item">
    <h2 class="accordion-header">
        <button class="accordion-button"><strong> Año 2016</strong></button>
    </h2>
    <div class="accordion-body"><div class="table-responsive">
        <table class="table">
            <tbody>
                <tr><td>Archivo</td><td>CSV</td></tr>
                <!-- ZZZZ
                <tr>
                    <td>Micro</td>
                    <td><a href="https://evaluaciones.evaluacion.gob.ec/BI/download/4203/" target="_blank"><img src="icn.png"/></a></td>
                </tr>
                -->
                <tr>
                    <td>Micro</td>
                    <td><a href="https://evaluaciones.evaluacion.gob.ec/BI/download/63317/?tmstv=1747432772" target="_blank"><img src="icn.png"/></a></td>
                </tr>
            </tbody>
        </table>
    </div></div>
</div>
</body></html>
"""

_EMPTY_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_cache():
    ineval_client._files_cache.clear()
    yield
    ineval_client._files_cache.clear()


def test_list_familias_returns_nine_fixed_familias():
    familias = ineval_client.list_familias()

    assert len(familias) == 9
    keys = {f["familia"] for f in familias}
    assert keys == {
        "ser_bachiller",
        "ser_estudiante",
        "ser_estudiante_infancia",
        "ser_estudiante_mitad_del_mundo",
        "ser_estudiante_galapagos",
        "ser_maestro",
        "ser_maestro_recategorizacion",
        "ser_profesional",
        "llece",
    }
    # Defensive copy, not the live list.
    familias[0]["familia"] = "mutated"
    assert ineval_client.list_familias()[0]["familia"] != "mutated"


@pytest.mark.asyncio
async def test_get_familia_archivos_parses_table_and_button_entries(httpx_mock):
    url = ineval_client._FAMILIAS_BY_KEY["ser_estudiante"]["url"]
    httpx_mock.add_response(url=url, html=_FAMILIA_HTML)

    result = await ineval_client.get_familia_archivos("ser_estudiante")

    assert result["familia"] == "ser_estudiante"
    assert result["nombre"] == "Ser Estudiante"
    # 4 table-cell links (Micro/CSV, Micro/Sintaxis, Factores/CSV,
    # Factores/SAV) + 2 standalone buttons (Fichas vigentes, Información
    # Estadística) = 6. The empty SAV cell for "Micro" must NOT appear.
    assert len(result["archivos"]) == 6

    micro_sintaxis = next(
        a for a in result["archivos"] if a["titulo"] == "Micro" and a["formato"] == "SINTAXIS"
    )
    assert micro_sintaxis["periodo"] == "Año lectivo 2024-2025"
    assert micro_sintaxis["url"].endswith("/download/76242/")
    assert micro_sintaxis["grupo"] is None

    factores_sav = next(
        a for a in result["archivos"] if a["titulo"] == "Factores Asociados estudiantes" and a["formato"] == "SAV"
    )
    assert factores_sav["url"].endswith("/download/76099/")

    # No "Micro"/SAV entry -- that cell was empty in the source table.
    assert not any(
        a["titulo"] == "Micro" and a["formato"] == "SAV" for a in result["archivos"]
    )

    fichas = next(a for a in result["archivos"] if a["titulo"] == "Descargar Fichas Metodológicas")
    assert fichas["periodo"] is None
    assert fichas["formato"] == "DESCONOCIDO"
    assert fichas["grupo"] == "Fichas metodológicas vigentes"

    stats = next(
        a for a in result["archivos"] if a["titulo"] == "Descargar promedios históricos de indicadores principales"
    )
    # This button sits AFTER the whole accordion -- periodo must not be
    # misattributed to the last year panel seen in the document.
    assert stats["periodo"] is None
    assert stats["grupo"] == "Información Estadística"


@pytest.mark.asyncio
async def test_get_familia_archivos_tags_llece_rounds_as_grupo(httpx_mock):
    url = ineval_client._FAMILIAS_BY_KEY["llece"]["url"]
    httpx_mock.add_response(url=url, html=_LLECE_HTML)

    result = await ineval_client.get_familia_archivos("llece")

    assert len(result["archivos"]) == 3
    erce = [a for a in result["archivos"] if a["grupo"] == "Erce"]
    serce = [a for a in result["archivos"] if a["grupo"] == "Serce"]
    assert len(erce) == 2
    assert len(serce) == 1
    assert erce[0]["periodo"] == "Año 2019"
    assert serce[0]["periodo"] == "Año 2006"


@pytest.mark.asyncio
async def test_get_familia_archivos_strips_commented_out_stale_row(httpx_mock, caplog):
    url = ineval_client._FAMILIAS_BY_KEY["ser_maestro"]["url"]
    httpx_mock.add_response(url=url, html=_COMMENTED_ROW_HTML)

    result = await ineval_client.get_familia_archivos("ser_maestro")

    # Only the live row (timestamped URL) must appear -- the commented-out
    # stale id (4203) must not leak through.
    assert len(result["archivos"]) == 1
    assert "63317" in result["archivos"][0]["url"]
    assert not any("4203" in a["url"] for a in result["archivos"])


@pytest.mark.asyncio
async def test_get_familia_archivos_rejects_unknown_familia():
    with pytest.raises(ValueError, match="no reconocida"):
        await ineval_client.get_familia_archivos("no-existe")


@pytest.mark.asyncio
async def test_off_domain_links_are_dropped_and_logged(httpx_mock, caplog):
    html = _FAMILIA_HTML.replace(
        "https://evaluaciones.evaluacion.gob.ec/BI/download/76242/",
        "https://evil.example.com/BI/download/76242/",
    )
    url = ineval_client._FAMILIAS_BY_KEY["ser_estudiante"]["url"]
    httpx_mock.add_response(url=url, html=html)

    with caplog.at_level("WARNING"):
        result = await ineval_client.get_familia_archivos("ser_estudiante")

    assert not any("evil.example.com" in a["url"] for a in result["archivos"])
    assert any("dominio inesperado" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_empty_parse_result_is_not_cached(httpx_mock):
    url = ineval_client._FAMILIAS_BY_KEY["ser_estudiante"]["url"]
    httpx_mock.add_response(url=url, html=_EMPTY_HTML)
    httpx_mock.add_response(url=url, html=_FAMILIA_HTML)

    first = await ineval_client.get_familia_archivos("ser_estudiante")
    assert first["archivos"] == []

    # A second call must re-fetch rather than serve the cached empty result.
    second = await ineval_client.get_familia_archivos("ser_estudiante")
    assert len(second["archivos"]) == 6


@pytest.mark.asyncio
async def test_concurrent_calls_for_same_uncached_familia_fetch_only_once(httpx_mock):
    url = ineval_client._FAMILIAS_BY_KEY["ser_estudiante"]["url"]
    httpx_mock.add_response(url=url, html=_FAMILIA_HTML)

    results = await asyncio.gather(
        ineval_client.get_familia_archivos("ser_estudiante"),
        ineval_client.get_familia_archivos("ser_estudiante"),
    )

    assert all(len(r["archivos"]) == 6 for r in results)
    # Only one response was registered above; a second real HTTP call would
    # raise inside httpx_mock, so reaching this point confirms dedup.
    assert len(httpx_mock.get_requests()) == 1

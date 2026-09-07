import asyncio

import pytest

from helpers import seps_client as seps

# Fixture HTML modeled directly on the real markup fetched live from
# estadisticas.seps.gob.ec/index.php/estadisticas-sfps/ on 2026-09-02 --
# same accordion/panel-body shape, same download-monitor link style
# (?sdm_process_download / ?smd_process_download), same <strong>-wrapped
# "current year" link, same grupo split for the segments panel.
_SFPS_HTML = """
<html><body>
<div class="panel">
<div class="panel-heading">
<h5 class="panel-title">
<a class="accordion-toggle" data-toggle="collapse" data-parent="#accordion-0" href="#collapse_0" aria-expanded="false">Estados Financieros Mensuales			</a><br />
</h5>
</p></div>
<div id="collapse_0" class="panel-collapse collapse" aria-labelledby="Estados Financieros Mensuales" data-parent="#accordion-0">
<div class="panel-body">
<p>Reportes que contienen los estados financieros de las entidades del Sector Financiero Popular y Solidario.</p>
<ul>
<li>Cooperativas de ahorro y crédito de los segmentos 1, 2, 3.
<ul>
<li style="list-style-type: none;">
<ul>
<li><a href="https://estadisticas.seps.gob.ec/?sdm_process_download=1&amp;download_id=3255">2026</a></li>
<li><a href="https://estadisticas.seps.gob.ec/?smd_process_download=1&amp;download_id=1655">2022</a></li>
</ul>
</li>
</ul>
</li>
</ul>
<ul>
<li>Cooperativas de ahorro y crédito de los segmentos 4 y 5.</li>
</ul>
<ul>
<li style="list-style-type: none;">
<ul>
<li><a href="https://estadisticas.seps.gob.ec/wp-content/uploads/2026/08/2026_EEFF_MEN_4-5.zip">2026</a></li>
</ul>
</li>
</ul>
</div></div>
</div>
<div class="panel">
<div class="panel-heading">
<h5 class="panel-title">
<a class="accordion-toggle" data-toggle="collapse" data-parent="#accordion-0" href="#collapse_3" aria-expanded="false">Calificación de Riesgos			</a><br />
</h5>
</p></div>
<div id="collapse_3" class="panel-collapse collapse" aria-labelledby="Calificación de Riesgos" data-parent="#accordion-0">
<div class="panel-body">
<p>Contiene información de la calificación de riesgos otorgada por las calificadoras autorizadas, se dispone de información de 112 entidades.</p>
<ul>
<li><strong><a href="https://estadisticas.seps.gob.ec/?sdm_process_download=1&amp;download_id=3525" target="_blank" rel="noopener">2026 con corte al 31 de marzo</a></strong></li>
<li><a href="https://estadisticas.seps.gob.ec/wp-content/uploads/2026/06/Publicacion-web-calificadoras_DICIEMBRE_2025_ok.pdf" target="_blank" rel="noopener">2025</a></li>
<li><a href="https://estadisticas.seps.gob.ec/?smd_process_download=1&amp;download_id=2084" target="_blank" rel="noopener">2022 </a></li>
<li><a href="https://otrositio.tech/fake/calificadoras.pdf" target="_blank" rel="noopener">2019 (dominio ajeno)</a></li>
</ul>
</div></div>
</div>
</body></html>
"""

_EPS_HTML = """
<html><body>
<div class="panel">
<div class="panel-heading">
<h5 class="panel-title">
<a class="accordion-toggle" data-toggle="collapse" data-parent="#accordion-0" href="#collapse_0" aria-expanded="false">Organizaciones EPS mensuales			</a><br />
</h5>
</p></div>
<div id="collapse_0" class="panel-collapse collapse" aria-labelledby="Organizaciones EPS mensuales" data-parent="#accordion-0">
<div class="panel-body">
<p>Reportes mensuales del número de organizaciones EPS.</p>
<ul>
<li><a href="https://estadisticas.seps.gob.ec/?sdm_process_download=1&amp;download_id=3290">2026</a></li>
<li><a href="https://estadisticas.seps.gob.ec/?sdm_process_download=1&amp;download_id=2810">2025</a></li>
</ul>
</div></div>
</div>
</body></html>
"""


@pytest.fixture(autouse=True)
def clear_cache():
    seps._page_cache.clear()
    yield
    seps._page_cache.clear()


def test_list_secciones_returns_26_fixed_secciones():
    secciones = seps.list_secciones()

    assert len(secciones) == 26
    keys = {s["seccion"] for s in secciones}
    assert "sfps_reportes_calificacion_de_riesgos" in keys
    assert "eps_datos_organizaciones_eps_mensuales" in keys
    # Every seccion key must be unique (no accidental duplicate slugs).
    assert len(keys) == len(secciones)

    secciones[0]["seccion"] = "mutated"
    assert seps.list_secciones()[0]["seccion"] != "mutated"


def test_clean_formato_known_and_unknown_extensions():
    assert seps._clean_formato("https://estadisticas.seps.gob.ec/a/b.pdf") == "PDF"
    assert seps._clean_formato("https://estadisticas.seps.gob.ec/a/b.zip") == "ZIP"
    # Download-monitor redirect links carry no extension in the URL itself.
    assert (
        seps._clean_formato("https://estadisticas.seps.gob.ec/?sdm_process_download=1&download_id=1")
        == "DESCONOCIDO"
    )


def test_is_seps_url():
    assert seps._is_seps_url("https://estadisticas.seps.gob.ec/wp-content/uploads/x.pdf")
    assert not seps._is_seps_url("https://otrositio.tech/fake/calificadoras.pdf")


def test_parse_panel_body_calificacion_de_riesgos_handles_strong_wrapped_link_and_bad_domain(
    caplog,
):
    bodies = {m.group("cid"): m.group("body") for m in seps._PANEL_BODY_RE.finditer(_SFPS_HTML)}
    assert "collapse_3" in bodies

    with caplog.at_level("WARNING"):
        parsed = seps._parse_panel_body(bodies["collapse_3"], "sfps_reportes_calificacion_de_riesgos")

    # 4 links in the fixture, one on a foreign domain that must be dropped.
    assert len(parsed["archivos"]) == 3
    titulos = [a["titulo"] for a in parsed["archivos"]]
    assert "2026 con corte al 31 de marzo" in titulos
    assert "2025" in titulos
    assert "2022" in titulos
    assert all(a["grupo"] is None for a in parsed["archivos"])
    assert "112 entidades" in parsed["descripcion"]
    assert any("dominio inesperado" in r.message for r in caplog.records)


def test_parse_page_extracts_grupo_split_for_estados_financieros_mensuales():
    parsed = seps._parse_page(_SFPS_HTML)

    assert set(parsed) == {"collapse_0", "collapse_3"}
    archivos = parsed["collapse_0"]["archivos"]
    assert len(archivos) == 3
    assert archivos[0]["grupo"] == "Cooperativas de ahorro y crédito de los segmentos 1, 2, 3."
    assert archivos[1]["grupo"] == "Cooperativas de ahorro y crédito de los segmentos 1, 2, 3."
    assert archivos[2]["grupo"] == "Cooperativas de ahorro y crédito de los segmentos 4 y 5."
    assert archivos[2]["formato"] == "ZIP"


@pytest.mark.asyncio
async def test_get_seccion_archivos_calificadoras(httpx_mock):
    httpx_mock.add_response(url=seps._SFPS_URL, html=_SFPS_HTML)

    result = await seps.get_seccion_archivos("sfps_reportes_calificacion_de_riesgos")

    assert result["seccion"] == "sfps_reportes_calificacion_de_riesgos"
    assert result["url"] == seps._SFPS_URL
    assert len(result["archivos"]) == 3
    assert "112 entidades" in result["descripcion"]


@pytest.mark.asyncio
async def test_get_seccion_archivos_rejects_unknown_seccion():
    with pytest.raises(ValueError, match="no reconocida"):
        await seps.get_seccion_archivos("no-existe")


@pytest.mark.asyncio
async def test_eps_seccion_fetches_eps_page_not_sfps(httpx_mock):
    httpx_mock.add_response(url=seps._EPS_URL, html=_EPS_HTML)

    result = await seps.get_seccion_archivos("eps_datos_organizaciones_eps_mensuales")

    assert len(result["archivos"]) == 2
    assert result["archivos"][0]["titulo"] == "2026"


@pytest.mark.asyncio
async def test_one_page_fetch_covers_every_seccion_on_it(httpx_mock):
    # sfps_reportes_calificacion_de_riesgos and
    # sfps_reportes_estados_financieros_mensuales are both on the SFPS
    # page -- only one HTTP request should be made for both.
    httpx_mock.add_response(url=seps._SFPS_URL, html=_SFPS_HTML)

    first = await seps.get_seccion_archivos("sfps_reportes_calificacion_de_riesgos")
    second = await seps.get_seccion_archivos("sfps_reportes_estados_financieros_mensuales")

    assert len(first["archivos"]) == 3
    assert len(second["archivos"]) == 3
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_empty_parse_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=seps._SFPS_URL, html="<html><body>Sitio en mantenimiento.</body></html>")
    httpx_mock.add_response(url=seps._SFPS_URL, html=_SFPS_HTML)

    first = await seps.get_seccion_archivos("sfps_reportes_calificacion_de_riesgos")
    assert first["archivos"] == []

    second = await seps.get_seccion_archivos("sfps_reportes_calificacion_de_riesgos")
    assert len(second["archivos"]) == 3


@pytest.mark.asyncio
async def test_concurrent_calls_for_same_uncached_pagina_fetch_only_once(httpx_mock):
    httpx_mock.add_response(url=seps._SFPS_URL, html=_SFPS_HTML)

    results = await asyncio.gather(
        seps.get_seccion_archivos("sfps_reportes_calificacion_de_riesgos"),
        seps.get_seccion_archivos("sfps_reportes_calificacion_de_riesgos"),
    )

    assert all(len(r["archivos"]) == 3 for r in results)
    assert len(httpx_mock.get_requests()) == 1

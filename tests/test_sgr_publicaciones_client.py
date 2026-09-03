import pytest

from helpers import sgr_publicaciones_client as client

# Trimmed but structurally faithful excerpt of the real
# https://www.gestionderiesgos.gob.ec/informes-de-situacion-actual-por-eventos-adversos-ecuador/
# markup (confirmed live 2026-09-03): <hr>-separated blocks, each a title
# anchor immediately followed by a "Fecha ...:" line ending in "| [ESTADO]"
# and a "Descripción:" line. Two label/markup variants are included
# (newer: "<strong>| <span>...", older: "| <strong><span>...") since both
# were observed live across the archive's 2016-2026 span.
_SITREP_INDEX_HTML = """
<html><body><section id="postcontent"><div class="row">
<div style="text-align: left;" align="center">
<p><strong><a href="https://www.gestionderiesgos.gob.ec/etapa-de-incendios-forestales-2026/">
<img src="icon.png"></a></strong></p>
<div align="center">
<div style="text-align: left;" align="center"><strong><a href="https://www.gestionderiesgos.gob.ec/etapa-de-incendios-forestales-2026/">Incendios Forestales 2026</a></strong></div>
<div style="text-align: left;" align="center"><strong>Fecha de ocurrencia:</strong> Desde el 01 de enero de 2026. <strong>| <span style="color: #ff0000;">[EN CURSO]</span></strong></div>
<div style="text-align: left;" align="center"><strong>Descripción:</strong> Las provincias con mayores perdidas son Tungurahua y Azuay.<br>
<strong>Fuente:</strong> Coordinaciones Zonales.</div>
</div>
</div>
<div align="center"><hr></div>
<div style="text-align: left;" align="center"><a href="http://www.gestionderiesgos.gob.ec/informes-de-situacion-actual-terremoto-magnitud-7-8/"><img src="icon2.png"></a><strong><a href="http://www.gestionderiesgos.gob.ec/informes-de-situacion-actual-terremoto-magnitud-7-8/">Terremoto 7.8 Mw Manabí, Pedernales</a></strong></div>
<div style="text-align: left;" align="center"><strong>Fecha del evento peligroso:</strong> 16 de abril de 2016. | <strong><span style="color: #008000;">[CERRADO]</span></strong></div>
<div style="text-align: left;" align="center"><strong>Descripción del evento peligroso:</strong> Sismo de Magnitud 7.8 en el norte de Ecuador.</div>
<div align="center"><hr></div>
</div></section></body></html>
"""

_EMPTY_SITREP_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"

# Trimmed excerpt of one real event page's PDF list (confirmed live
# 2026-09-03): section headings ("SITREP NACIONALES:", "SITREP
# PROVINCIALES – AZUAY:") followed by plain <a href=".../wp-content/
# uploads/YYYY/MM/....pdf"> links.
_SITREP_EVENT_HTML = """
<html><body>
<div><strong>SITREP NACIONALES:</strong></div>
<p><a href="https://www.gestionderiesgos.gob.ec/wp-content/uploads/2026/07/SitRep-No-135-Lluvias-01012026-al-30072026-12h00.pdf">SITREP Nacional No. 135– 01/01/2026 al 30/07/2026</a></p>
<p><a href="https://www.gestionderiesgos.gob.ec/wp-content/uploads/2026/07/Infografia-en-referencia-a-Sitrep-No-135-30072026.pdf">Infografía Nacional No. 135</a></p>
<div><strong>SITREP PROVINCIALES – AZUAY:</strong></div>
<p><a href="https://www.gestionderiesgos.gob.ec/wp-content/uploads/2026/07/SitRep-No-12-Lluvias-Azuay_01012026_al_20072026_14h00.pdf">Informe de Situación No. 12 Azuay – 20/07/2026</a></p>
<p><a href="https://www.gobiernoelectronico.gob.ec/wp-content/uploads/2019/07/Acuerdo-012-2019.pdf" class="cc-link">Acuerdo No. 012-2019</a></p>
</body></html>
"""

_EMPTY_EVENT_HTML = "<html><body><p>Página en construcción.</p></body></html>"

# Trimmed but structurally faithful excerpt of the real
# https://www.gestionderiesgos.gob.ec/biblioteca/ markup (confirmed live
# 2026-09-03): a "ul-downloads" root holding top-level "li-gray1" category
# items (id="cat-N"), each with its own "Descargar <TITLE>" download-
# monitor entries directly, or nested category items sharing the exact
# same markup (confirmed live: "Mapas de Tsunami" > "Galápagos" /
# "Manabí") -- included here to exercise _top_level_categorias' depth
# tracking, not just a flat accordion.
_BIBLIOTECA_HTML = """
<html><body>
<ul class="ul-downloads">
<li class="li-gray1" id="cat-1523">
    <a style="display: block; padding: 10px 0px;background: #F8F8F8;"><span class="ico">+</span>Reformas</a>
    <ul style="display: none; padding-left: 15px;"><li class="li-gray4"><div style="width:100%;"><div style="width:80%; float:left; margin:10px auto; padding-left: 10px;"><span class="titulo">RESOLUCION No. SNGRE-037-2020</span><br>RESOLUCION CONSOLIDADA</div><div style="width:20%; float:left;"><span class="link">
    <a href="https://www.gestionderiesgos.gob.ec/wp-content/plugins/download-monitor/download.php?id=7891&amp;force=0" title="Ver RESOLUCION No. SNGRE-037-2020" target="_blank" class="ver">ver</a>&nbsp;
    <a href="https://www.gestionderiesgos.gob.ec/wp-content/plugins/download-monitor/download.php?id=7891&amp;force=1" title="Descargar RESOLUCION No. SNGRE-037-2020">descarga</a>
    </span></div><div style="clear:both"></div></div></li></ul>
    <ul style="display: none; padding-left: 15px;"><li class="li-gray4"><div style="width:100%;"><div style="width:80%; float:left; margin:10px auto; padding-left: 10px;"><span class="titulo">RESOLUCION No. SNGRE-035-2020</span><br>Licencias ArcGis</div><div style="width:20%; float:left;"><span class="link">
    <a href="https://www.gestionderiesgos.gob.ec/wp-content/plugins/download-monitor/download.php?id=7890&amp;force=0" title="Ver RESOLUCION No. SNGRE-035-2020" target="_blank" class="ver">ver</a>&nbsp;
    <a href="https://www.gestionderiesgos.gob.ec/wp-content/plugins/download-monitor/download.php?id=7890&amp;force=1" title="Descargar RESOLUCION No. SNGRE-035-2020">descarga</a>
    </span></div><div style="clear:both"></div></div></li></ul>
</li>
<li class="li-gray1" id="cat-204">
    <a style="display: block; padding: 10px 0px;background: #F8F8F8;"><span class="ico">+</span>Mapas de Tsunami</a>
    <ul style="display: none; padding-left: 15px;"><li class="li-gray1" id="cat-205">
        <a style="display: block; padding: 10px 0px;background: #F8F8F8;"><span class="ico">+</span>Galápagos</a>
        <ul style="display: none; padding-left: 15px;"><li class="li-gray4"><div style="width:100%;"><div style="width:80%; float:left; margin:10px auto; padding-left: 10px;"><span class="titulo">Puerto Villamil</span><br></div><div style="width:20%; float:left;"><span class="link">
        <a href="https://www.gestionderiesgos.gob.ec/wp-content/plugins/download-monitor/download.php?id=1623&amp;force=0" title="Ver Puerto Villamil" target="_blank" class="ver">ver</a>&nbsp;
        <a href="https://www.gestionderiesgos.gob.ec/wp-content/plugins/download-monitor/download.php?id=1623&amp;force=1" title="Descargar Puerto Villamil">descarga</a>
        </span></div><div style="clear:both"></div></div></li></ul>
    </li>
    <li class="li-gray1" id="cat-206">
        <a style="display: block; padding: 10px 0px;background: #F8F8F8;"><span class="ico">+</span>Manabí</a>
        <ul style="display: none; padding-left: 15px;"><li class="li-gray4"><div style="width:100%;"><div style="width:80%; float:left; margin:10px auto; padding-left: 10px;"><span class="titulo">Manta</span><br></div><div style="width:20%; float:left;"><span class="link">
        <a href="https://www.gestionderiesgos.gob.ec/wp-content/plugins/download-monitor/download.php?id=5300&amp;force=0" title="Ver Manta" target="_blank" class="ver">ver</a>&nbsp;
        <a href="https://www.gestionderiesgos.gob.ec/wp-content/plugins/download-monitor/download.php?id=5300&amp;force=1" title="Descargar Manta">descarga</a>
        </span></div><div style="clear:both"></div></div></li></ul>
    </li></ul>
</li>
</ul>
</body></html>
"""

_EMPTY_BIBLIOTECA_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"


@pytest.fixture(autouse=True)
def clear_caches():
    client._sitrep_index_cache.clear()
    client._biblioteca_cache.clear()
    client._sitrep_event_cache.clear()
    yield
    client._sitrep_index_cache.clear()
    client._biblioteca_cache.clear()
    client._sitrep_event_cache.clear()


# --- SITREP archive (event index) ---


@pytest.mark.asyncio
async def test_list_eventos_sitrep_parses_all_events(httpx_mock):
    httpx_mock.add_response(url=client._SITREP_INDEX_URL, html=_SITREP_INDEX_HTML)

    result = await client.list_eventos_sitrep()

    assert result["total"] == 2
    assert result["total_en_pagina"] == 2
    assert result["source"].startswith("SGR")
    eventos = {e["titulo"]: e for e in result["eventos"]}
    assert "Incendios Forestales 2026" in eventos
    assert "Terremoto 7.8 Mw Manabí, Pedernales" in eventos

    reciente = eventos["Incendios Forestales 2026"]
    assert reciente["estado"] == "EN CURSO"
    assert "2026" in reciente["fecha_texto"]
    assert "Tungurahua" in reciente["descripcion"]
    assert reciente["url"] == "https://www.gestionderiesgos.gob.ec/etapa-de-incendios-forestales-2026/"

    antiguo = eventos["Terremoto 7.8 Mw Manabí, Pedernales"]
    assert antiguo["estado"] == "CERRADO"
    assert "2016" in antiguo["fecha_texto"]


@pytest.mark.asyncio
async def test_list_eventos_sitrep_filters_by_query(httpx_mock):
    httpx_mock.add_response(url=client._SITREP_INDEX_URL, html=_SITREP_INDEX_HTML)

    result = await client.list_eventos_sitrep(query="terremoto")

    assert result["total"] == 1
    assert result["eventos"][0]["titulo"] == "Terremoto 7.8 Mw Manabí, Pedernales"


@pytest.mark.asyncio
async def test_list_eventos_sitrep_filters_by_estado_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=client._SITREP_INDEX_URL, html=_SITREP_INDEX_HTML)

    result = await client.list_eventos_sitrep(query="en curso")

    assert result["total"] == 1
    assert result["eventos"][0]["estado"] == "EN CURSO"


@pytest.mark.asyncio
async def test_empty_sitrep_index_scrape_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=client._SITREP_INDEX_URL, html=_EMPTY_SITREP_HTML)
    httpx_mock.add_response(url=client._SITREP_INDEX_URL, html=_SITREP_INDEX_HTML)

    first = await client.list_eventos_sitrep()
    assert first["total_en_pagina"] == 0

    second = await client.list_eventos_sitrep()
    assert second["total_en_pagina"] == 2


# --- SITREP archive (one event's PDF list) ---


@pytest.mark.asyncio
async def test_get_sitrep_archivos_parses_pdfs_and_tags_grupo(httpx_mock):
    evento_url = "https://www.gestionderiesgos.gob.ec/sitrep-afectaciones-por-lluvias-2025-2026/"
    httpx_mock.add_response(url=evento_url, html=_SITREP_EVENT_HTML)

    result = await client.get_sitrep_archivos(evento_url)

    # 2 national entries (SITREP + Infografía) + 1 provincial entry.
    assert result["total"] == 3
    archivos = {a["titulo"]: a for a in result["archivos"]}
    nacional = archivos["SITREP Nacional No. 135– 01/01/2026 al 30/07/2026"]
    assert nacional["grupo"] == "SITREP NACIONALES:"
    assert nacional["formato"] == "PDF"
    assert archivos["Infografía Nacional No. 135"]["grupo"] == "SITREP NACIONALES:"

    provincial = archivos["Informe de Situación No. 12 Azuay – 20/07/2026"]
    assert provincial["grupo"] == "SITREP PROVINCIALES – AZUAY:"

    # The unrelated cross-domain cookie-consent link must not leak in.
    assert "Acuerdo No. 012-2019" not in archivos


@pytest.mark.asyncio
async def test_get_sitrep_archivos_rejects_foreign_domain():
    with pytest.raises(ValueError):
        await client.get_sitrep_archivos("https://www.example.com/not-sgr/")


@pytest.mark.asyncio
async def test_empty_event_scrape_is_not_cached(httpx_mock):
    evento_url = "https://www.gestionderiesgos.gob.ec/algun-evento/"
    httpx_mock.add_response(url=evento_url, html=_EMPTY_EVENT_HTML)
    httpx_mock.add_response(url=evento_url, html=_SITREP_EVENT_HTML)

    first = await client.get_sitrep_archivos(evento_url)
    assert first["total"] == 0

    second = await client.get_sitrep_archivos(evento_url)
    assert second["total"] == 3


# --- Biblioteca ---


@pytest.mark.asyncio
async def test_list_biblioteca_categorias_returns_only_top_level(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    result = await client.list_biblioteca_categorias()

    assert result["total"] == 2
    nombres = {c["nombre"]: c for c in result["categorias"]}
    assert "Reformas" in nombres
    assert "Mapas de Tsunami" in nombres
    # The nested "Galápagos"/"Manabí" sub-categories must not appear as
    # their own top-level entries.
    assert "Galápagos" not in nombres
    assert "Manabí" not in nombres

    assert nombres["Reformas"]["total_archivos"] == 2
    assert nombres["Mapas de Tsunami"]["total_archivos"] == 2


@pytest.mark.asyncio
async def test_get_biblioteca_categoria_archivos_flat_category(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    result = await client.get_biblioteca_categoria_archivos("Reformas")

    assert result["total"] == 2
    ids = {a["id"] for a in result["archivos"]}
    assert ids == {"7891", "7890"}
    assert all(a["subgrupo"] is None for a in result["archivos"])
    assert all(a["formato"] == "DESCONOCIDO" for a in result["archivos"])


@pytest.mark.asyncio
async def test_get_biblioteca_categoria_archivos_nested_category_by_id(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    result = await client.get_biblioteca_categoria_archivos("204")

    assert result["nombre"] == "Mapas de Tsunami"
    assert result["total"] == 2
    by_title = {a["titulo"]: a for a in result["archivos"]}
    assert by_title["Puerto Villamil"]["subgrupo"] == "Galápagos"
    assert by_title["Manta"]["subgrupo"] == "Manabí"


@pytest.mark.asyncio
async def test_get_biblioteca_categoria_archivos_unknown_raises(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    with pytest.raises(ValueError):
        await client.get_biblioteca_categoria_archivos("no-existe")


@pytest.mark.asyncio
async def test_empty_biblioteca_scrape_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_EMPTY_BIBLIOTECA_HTML)
    httpx_mock.add_response(url=client._BIBLIOTECA_URL, html=_BIBLIOTECA_HTML)

    first = await client.list_biblioteca_categorias()
    assert first["total"] == 0

    second = await client.list_biblioteca_categorias()
    assert second["total"] == 2

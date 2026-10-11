import re

import pytest

from helpers import cne_client

# Trimmed from the real markup observed live 2026-10-10 on
# www.cne.gob.ec/estadisticas/bases-de-datos/: the process accordion plus the
# inline script that carries the WPDM nonce.
_PAGE_HTML = """
<html><body>
<script>var u = "https://www.cne.gob.ec/?wpdmactask=listsub&__wpdmacn=a7bcbf6abe&parent=";</script>
<div class="card-header"><a class="accord-handle" data-toggle="collapse"
  data-parent="#accordion-1" href="#z8325-1" rel="8325">Elecciones Generales 2025</a></div>
<div class="card-header"><a class="accord-handle" data-toggle="collapse"
  data-parent="#accordion-1" href="#z6924-1" rel="6924">Elecciones Generales 2021</a></div>
<div class="card-header"><a class="accord-handle" data-toggle="collapse"
  data-parent="#accordion-1" href="#z8376-1" rel="8376">Referéndum y Consulta Popular 2025</a></div>
</body></html>
"""

# listsub for the process: only child categories ("Loading..." placeholders).
_PROCESO_HTML = """
<div id="accordion-8325" class="panel-group accordion">
<div class="card"><div class="card-header"><a data-toggle="collapse" class="accord-handle"
  data-parent="#accordion-8325" href="#z8328-1" rel="8328">Registro Electoral</a></div>
<div id="z8328-1" class="panel-collapse collapse"><div class="card-body" id="ac-body-8328">
<div id="8328"><i class="fa fa-spinner fa-spin"></i> Loading...</div></div></div></div>
<div class="card"><div class="card-header"><a data-toggle="collapse" class="accord-handle"
  data-parent="#accordion-8325" href="#z8329-1" rel="8329">Resultados</a></div>
<div id="z8329-1" class="panel-collapse collapse"><div class="card-body" id="ac-body-8329">
<div id="8329"><i class="fa fa-spinner fa-spin"></i> Loading...</div></div></div></div>
</div>
<ul class="list-group mt-2" style="padding: 0 !important;"></ul>
"""

_FILE_TPL = """
<li class="list-group-item"><div class="wpdm-link-tpl link-btn [color]"
 data-durl="https://www.cne.gob.ec/download/{slug}/?wpdmdl={id}&refresh=6acadd3f4b4881791679807" >
<div class="media"><div class="pull-left"><img src="data:image/svg+xml;base64,AAAA" /></div>
<div class="media-body"><strong class="ptitle">{title} <span class="label label-default"
 style="font-weight: 400;">{n} descargas</span>&nbsp;<span class="label label-default"
 style="font-weight: 400;">{size}</span></strong>
<div><strong><a class='wpdm-download-link btn btn-secondary ' rel='nofollow'
 href='https://www.cne.gob.ec/download/{slug}/?wpdmdl={id}&refresh=x'>Descargar</a></strong></div>
</div></div></div></li>
"""

_REGISTRO_HTML = (
    '<div id="accordion-8328" class="panel-group accordion"></div>'
    '<ul class="list-group">'
    + _FILE_TPL.format(
        slug="registro-electoral-a-nivel-parroquial-5",
        id=57394,
        title="Registro Electoral a nivel parroquial",
        n=850,
        size="457.89 KB",
    )
    + "</ul>"
)
_RESULTADOS_HTML = (
    '<div id="accordion-8329" class="panel-group accordion"></div>'
    '<ul class="list-group">'
    + _FILE_TPL.format(
        slug="segunda-vuelta-2", id=57399, title="Segunda Vuelta", n=1336, size="703.80 KB"
    )
    + _FILE_TPL.format(
        slug="primera-vuelta-2", id=57396, title="Primera Vuelta", n="1,962", size="18.12 MB"
    )
    + "</ul>"
)


def _listsub(parent: str) -> re.Pattern[str]:
    return re.compile(rf".*wpdmactask=listsub.*&parent={parent}$")


@pytest.fixture(autouse=True)
def clear_caches():
    cne_client._index_cache.clear()
    cne_client._files_cache.clear()
    yield
    cne_client._index_cache.clear()
    cne_client._files_cache.clear()


def _mock_proceso(httpx_mock):
    httpx_mock.add_response(url=cne_client._PAGE_URL, html=_PAGE_HTML)
    httpx_mock.add_response(url=_listsub("8325"), html=_PROCESO_HTML)
    httpx_mock.add_response(url=_listsub("8328"), html=_REGISTRO_HTML)
    httpx_mock.add_response(url=_listsub("8329"), html=_RESULTADOS_HTML)


@pytest.mark.asyncio
async def test_list_procesos_reads_the_accordion(httpx_mock):
    httpx_mock.add_response(url=cne_client._PAGE_URL, html=_PAGE_HTML)

    result = await cne_client.list_procesos()

    assert result["url_fuente"] == cne_client._PAGE_URL
    assert result["categorias"] == [
        {"id": "8325", "nombre": "Elecciones Generales 2025"},
        {"id": "6924", "nombre": "Elecciones Generales 2021"},
        {"id": "8376", "nombre": "Referéndum y Consulta Popular 2025"},
    ]


@pytest.mark.asyncio
async def test_get_proceso_archivos_crawls_subcategories(httpx_mock):
    _mock_proceso(httpx_mock)

    result = await cne_client.get_proceso_archivos("8325")

    assert result["id"] == "8325"
    assert result["nombre"] == "Elecciones Generales 2025"
    assert len(result["archivos"]) == 3
    segunda = next(a for a in result["archivos"] if a["titulo"] == "Segunda Vuelta")
    assert segunda["grupo"] == "Resultados"
    assert segunda["tamano"] == "703.80 KB"
    assert segunda["descargas"] == 1336
    # The per-request refresh token is dropped; the bare wpdmdl URL downloads.
    assert segunda["url"] == "https://www.cne.gob.ec/download/segunda-vuelta-2/?wpdmdl=57399"
    primera = next(a for a in result["archivos"] if a["titulo"] == "Primera Vuelta")
    assert primera["descargas"] == 1962
    assert primera["tamano"] == "18.12 MB"
    registro = next(a for a in result["archivos"] if a["grupo"] == "Registro Electoral")
    assert registro["formato"] == "DESCONOCIDO"


@pytest.mark.asyncio
async def test_get_proceso_archivos_accepts_name_and_caches(httpx_mock):
    _mock_proceso(httpx_mock)

    first = await cne_client.get_proceso_archivos("elecciones generales 2025")
    # Second call is served from cache: no further mocked responses needed.
    second = await cne_client.get_proceso_archivos("8325")

    assert first is second


@pytest.mark.asyncio
async def test_ambiguous_or_unknown_proceso_raises(httpx_mock):
    httpx_mock.add_response(url=cne_client._PAGE_URL, html=_PAGE_HTML)

    with pytest.raises(ValueError, match="varios procesos"):
        await cne_client.get_proceso_archivos("Elecciones Generales")
    with pytest.raises(ValueError, match="no reconocido"):
        await cne_client.get_proceso_archivos("Elecciones 1990")


@pytest.mark.asyncio
async def test_rejected_nonce_reloads_the_index_once(httpx_mock):
    httpx_mock.add_response(url=cne_client._PAGE_URL, html=_PAGE_HTML)
    httpx_mock.add_response(url=_listsub("8325"), text="-1")
    # Reload of the page, then the listing succeeds with the new nonce.
    httpx_mock.add_response(url=cne_client._PAGE_URL, html=_PAGE_HTML.replace("a7bcbf6abe", "ffffffffff"))
    httpx_mock.add_response(url=_listsub("8325"), html=_PROCESO_HTML)
    httpx_mock.add_response(url=_listsub("8328"), html=_REGISTRO_HTML)
    httpx_mock.add_response(url=_listsub("8329"), html=_RESULTADOS_HTML)

    result = await cne_client.get_proceso_archivos("8325")

    assert len(result["archivos"]) == 3
    nonces = [r.url.params["__wpdmacn"] for r in httpx_mock.get_requests() if "listsub" in str(r.url)]
    assert nonces[0] == "a7bcbf6abe"
    assert nonces[-1] == "ffffffffff"


@pytest.mark.asyncio
async def test_page_without_processes_raises(httpx_mock):
    httpx_mock.add_response(url=cne_client._PAGE_URL, html="<html>Request unsuccessful.</html>")

    with pytest.raises(ValueError, match="no trae la lista"):
        await cne_client.list_procesos()


def test_foreign_file_links_are_dropped():
    html = _FILE_TPL.format(slug="x", id=1, title="Bueno", n=1, size="1 KB") + _FILE_TPL.format(
        slug="x", id=2, title="Malo", n=1, size="1 KB"
    ).replace("www.cne.gob.ec/download", "evil.example/download", 1)

    archivos = cne_client._parse_files(html)

    assert [a["titulo"] for a in archivos] == ["Bueno"]

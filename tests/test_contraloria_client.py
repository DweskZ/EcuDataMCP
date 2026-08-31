import pytest

from helpers import contraloria_client

_PAGE_HTML = """
<html><body>
<div class="row"><div class="col-sm-11">Informes aprobados enero - marzo 2023</div><div class="col-sm-1"><input type="button" class="icono_descargar_documento" title="Descargar documento seleccionado" onclick="javascript: down('pesdoc', 67);" /></div></div>
<div class="row"><div class="col-sm-11">Glosario</div><div class="col-sm-1"><input type="button" class="icono_descargar_documento" title="Descargar documento seleccionado" onclick="javascript: down('pesdoc', 68);" /></div></div>
<div class="row"><div class="col-sm-11">Informes aprobados abril - junio 2023</div><div class="col-sm-1"><input type="button" class="icono_descargar_documento" title="Descargar documento seleccionado" onclick="javascript: down('pesdoc', 81);" /></div></div>
</body></html>
"""

_PLAN_ANUAL_PAGE_HTML = """
<html><body>
<div class="row"><div class="col-sm-11">Acuerdo aprobación Plan anual de control 2025</div><div class="col-sm-1"><input type="button" class="icono_descargar_documento" title="Descargar documento seleccionado" onclick="javascript: down('doc', 2812);" /></div></div>
<div class="row"><div class="col-sm-11">Acuerdo aprobación Plan anual de control 2024</div><div class="col-sm-1"><input type="button" class="icono_descargar_documento" title="Descargar documento seleccionado" onclick="javascript: down('doc', 2775);" /></div></div>
</body></html>
"""

_EMPTY_PAGE_HTML = "<html><body><p>Sitio en mantenimiento.</p></body></html>"

# Real exports use ';' delimiters and are not UTF-8 (Windows-1252) —
# exercised here via a Latin-1 byte sequence for "Aprobación".
_CSV_TEXT = (
    "N°;Unidad de Control;Entidad;Diligencia;Periodo Desde;Periodo Hasta;"
    "Tipo de informe;N° Informe;Fecha Aprobación\r\n"
    "355;DNA 3;MINISTERIO DE ECONOMÍA Y FINANZAS;Examen Especial;"
    "01/01/2023;31/03/2023;Examen Especial;DNA3-0001-2023;15/04/2023\r\n"
)
_CSV_BYTES = _CSV_TEXT.encode("cp1252")


@pytest.fixture(autouse=True)
def clear_cache():
    contraloria_client._informes_cache.clear()
    yield
    contraloria_client._informes_cache.clear()


@pytest.mark.asyncio
async def test_list_informes(httpx_mock):
    httpx_mock.add_response(url=contraloria_client._SEED_URL, html=_PAGE_HTML)
    httpx_mock.add_response(
        url=contraloria_client._PLAN_ANUAL_SEED_URL, html=_PLAN_ANUAL_PAGE_HTML
    )

    informes = await contraloria_client.list_informes()

    assert len(informes) == 5
    first = informes[0]
    assert first["id"] == "67"
    assert first["tipo"] == "pesdoc"
    assert first["label"] == "Informes aprobados enero - marzo 2023"
    assert first["url"] == (
        "https://www.contraloria.gob.ec/WFDescarga.aspx?id=67&tipo=pesdoc&op=d"
    )
    plan_2025 = next(i for i in informes if i["id"] == "2812")
    assert plan_2025["tipo"] == "doc"
    assert plan_2025["label"] == "Acuerdo aprobación Plan anual de control 2025"


@pytest.mark.asyncio
async def test_get_informe_downloads_and_parses_csv(httpx_mock):
    httpx_mock.add_response(url=contraloria_client._SEED_URL, html=_PAGE_HTML)
    httpx_mock.add_response(
        url=contraloria_client._PLAN_ANUAL_SEED_URL, html=_PLAN_ANUAL_PAGE_HTML
    )
    httpx_mock.add_response(
        url="https://www.contraloria.gob.ec/WFDescarga.aspx?id=67&tipo=pesdoc&op=d",
        content=_CSV_BYTES,
        headers={"content-type": "text/csv"},
    )

    result = await contraloria_client.get_informe("67")

    assert result["label"] == "Informes aprobados enero - marzo 2023"
    assert "Entidad" in result["headers"]
    assert result["rows"][0][2] == "MINISTERIO DE ECONOMÍA Y FINANZAS"


@pytest.mark.asyncio
async def test_get_informe_returns_metadata_only_for_plan_anual_pdf(httpx_mock):
    httpx_mock.add_response(url=contraloria_client._SEED_URL, html=_PAGE_HTML)
    httpx_mock.add_response(
        url=contraloria_client._PLAN_ANUAL_SEED_URL, html=_PLAN_ANUAL_PAGE_HTML
    )

    result = await contraloria_client.get_informe("2812")

    assert result["is_pdf"] is True
    assert result["tipo"] == "doc"
    assert result["label"] == "Acuerdo aprobación Plan anual de control 2025"
    assert result["url"] == (
        "https://www.contraloria.gob.ec/WFDescarga.aspx?id=2812&tipo=doc&op=d"
    )


@pytest.mark.asyncio
async def test_get_informe_rejects_unknown_id(httpx_mock):
    httpx_mock.add_response(url=contraloria_client._SEED_URL, html=_PAGE_HTML)
    httpx_mock.add_response(
        url=contraloria_client._PLAN_ANUAL_SEED_URL, html=_PLAN_ANUAL_PAGE_HTML
    )

    with pytest.raises(ValueError, match="no encontrado"):
        await contraloria_client.get_informe("999")


@pytest.mark.asyncio
async def test_empty_scrape_result_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=contraloria_client._SEED_URL, html=_EMPTY_PAGE_HTML)
    httpx_mock.add_response(
        url=contraloria_client._PLAN_ANUAL_SEED_URL, html=_EMPTY_PAGE_HTML
    )
    httpx_mock.add_response(url=contraloria_client._SEED_URL, html=_PAGE_HTML)
    httpx_mock.add_response(
        url=contraloria_client._PLAN_ANUAL_SEED_URL, html=_PLAN_ANUAL_PAGE_HTML
    )

    first = await contraloria_client.list_informes()
    assert first == []

    second = await contraloria_client.list_informes()
    assert len(second) == 5

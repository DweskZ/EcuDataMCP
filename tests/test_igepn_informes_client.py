import pytest

from helpers import igepn_informes_client as c

_INITIAL_HTML = (
    '<html><body><form id="form">'
    '<input type="hidden" name="javax.faces.ViewState" '
    'id="j_id1:javax.faces.ViewState:0" value="INITIAL-VS" autocomplete="off" />'
    "</form></body></html>"
)


def _row(idx: int, nombre: str, volcan: str, version: str, fecha: str) -> str:
    return (
        f'<li class="ui-dataview-row">'
        f'<label>Nombre:</label></td><td><label>{nombre}<'
        f'</label></td></tr><tr><td><label>Volcán:</label></td><td><label>{volcan}<'
        f'</label></td></tr><tr><td><label>Versión:</label></td><td><label>{version}<'
        f'</label></td></tr><tr><td><label>Fecha Publicación Informe:</label></td>'
        f'<td><label>{fecha}<'
        f'<button id="form:j_idt42:{idx}:j_idt64">Descargar Informe</button>'
        f"</li>"
    )


def _partial_response(rows_html: str, viewstate: str = "SEARCH-VS") -> str:
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<partial-response><changes><update id="form"><![CDATA[
<ul class="ui-dataview-list-container">{rows_html}</ul>
<input type="hidden" name="javax.faces.ViewState" id="j_id1:javax.faces.ViewState:0" />
<script>PrimeFaces</script>
]]></update>
<update id="javax.faces.ViewState"><![CDATA[{viewstate}]]></update>
</changes></partial-response>"""


_TWO_ROWS_XML = _partial_response(
    _row(0, "Informe Diario 2022-071", "Cotopaxi", "1", "2022-12-31 12:22:44")
    + _row(1, "Informe Diario 2022-365", "El Reventador", "1", "2022-12-31 12:12:56")
    + _row(2, "Informe Diario 2022-365", "Sangay", "1", "2022-12-31 12:19:32")
)


async def test_search_informes_parses_rows_and_filters_client_side(httpx_mock):
    httpx_mock.add_response(method="GET", html=_INITIAL_HTML)
    httpx_mock.add_response(method="POST", text=_TWO_ROWS_XML)

    result = await c.search_informes(query="cotopaxi", grupo="volcanico", anio=2022)

    assert result["grupo"] == "volcanico"
    assert result["anio"] == 2022
    assert result["total_en_pagina"] == 3
    assert result["coincidencias"] == 1
    assert result["informes"][0]["nombre"] == "Informe Diario 2022-071"
    assert result["informes"][0]["volcan"] == "Cotopaxi"
    assert "_button_id" not in result["informes"][0]


async def test_search_informes_invalid_grupo():
    with pytest.raises(ValueError, match="grupo"):
        await c.search_informes(grupo="lunar")


async def test_download_informe_success(httpx_mock):
    httpx_mock.add_response(method="GET", html=_INITIAL_HTML)
    httpx_mock.add_response(method="POST", text=_TWO_ROWS_XML)
    httpx_mock.add_response(
        method="POST", content=b"%PDF-1.4 fake", headers={"content-type": "application/pdf"}
    )

    raw, nombre = await c.download_informe(
        "Informe Diario 2022-365", volcan="Sangay", grupo="volcanico", anio=2022
    )
    assert raw == b"%PDF-1.4 fake"
    assert nombre == "Informe Diario 2022-365"


async def test_download_informe_ambiguous_name_without_volcan(httpx_mock):
    httpx_mock.add_response(method="GET", html=_INITIAL_HTML)
    httpx_mock.add_response(method="POST", text=_TWO_ROWS_XML)

    with pytest.raises(ValueError, match="especifica 'volcan'"):
        await c.download_informe("Informe Diario 2022-365", grupo="volcanico", anio=2022)


async def test_download_informe_not_found(httpx_mock):
    httpx_mock.add_response(method="GET", html=_INITIAL_HTML)
    httpx_mock.add_response(method="POST", text=_TWO_ROWS_XML)

    with pytest.raises(ValueError, match="No se encontró"):
        await c.download_informe("Informe Que No Existe", grupo="volcanico", anio=2022)


async def test_download_informe_non_pdf_response(httpx_mock):
    httpx_mock.add_response(method="GET", html=_INITIAL_HTML)
    httpx_mock.add_response(method="POST", text=_TWO_ROWS_XML)
    httpx_mock.add_response(
        method="POST", text="<html>error</html>", headers={"content-type": "text/html"}
    )

    with pytest.raises(ValueError, match="no devolvió un PDF"):
        await c.download_informe(
            "Informe Diario 2022-071", grupo="volcanico", anio=2022
        )

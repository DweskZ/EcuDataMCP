import pytest

from helpers import iess_client

# --- Boletines Estadísticos fixtures -----------------------------------
# Trimmed from the real page structure confirmed live 2026-09-04
# (iess.gob.ec/es/estadisticas): a table row's col-1 cell links to a
# Liferay document_library_display "view" page, titled via a
# taglib-text span. "Mostrando el intervalo ..." states the real total
# so a >20-result page (page1 here claims 21) triggers pagination.

_BOL_PAGE1_HTML = """
<html><body>
<div class="search-results">
  Mostrando el intervalo 1 - 20 de 21 resultados.
</div>
<table>
<tr><td>
<a href="https://www.iess.gob.ec/es/estadisticas/-/document_library_display/zIm8/view/8421754/171705?_110_INSTANCE_zIm8_redirect=x">
  <span><img class="icon" src="/x/small/_sprite.png" /><span class="taglib-text">06_BOLETIN ESTADISTICO 29 2024.pdf</span></span>
</a>
</td></tr>
<tr><td>
<a href="https://www.iess.gob.ec/es/estadisticas/-/document_library_display/zIm8/view/8421754/151612?_110_INSTANCE_zIm8_redirect=x">
  <span><img class="icon" src="/x/small/_sprite.png" /><span class="taglib-text">07_BOLETIN_ESTADISTICO_28_2023</span></span>
</a>
</td></tr>
</table>
</body></html>
"""

_BOL_PAGE2_URL = (
    "https://www.iess.gob.ec/es/estadisticas?p_p_id=110_INSTANCE_zIm8"
    "&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&p_p_col_id=column-1"
    "&p_p_col_pos=1&p_p_col_count=3&_110_INSTANCE_zIm8_cur2=2"
    "&_110_INSTANCE_zIm8_delta2=20"
)

_BOL_PAGE2_HTML = """
<html><body>
<a href="https://www.iess.gob.ec/es/estadisticas/-/document_library_display/zIm8/view/8421754/50202?_110_INSTANCE_zIm8_redirect=x">
  <span><img class="icon" src="/x/small/_sprite.png" /><span class="taglib-text">31_BOLETIN ESTADISTICO 01 1978</span></span>
</a>
</body></html>
"""


def _bol_detail_html(url: str) -> str:
    # Real detail-page shape: the "Descargar" action is a taglib-icon
    # anchor whose <img> icon filename (large/<ext>.png) is the format
    # signal -- not the URL's own (frequently missing) extension.
    return f"""
    <html><body>
    <a class="taglib-icon" href="{url}" target="_blank" title="(Abre una nueva ventana)" >
      <img class="icon" src="/iess-interno-theme/images/file_system/large/pdf.png" alt="Descargar" title="Descargar" />
    </a>
    </body></html>
    """


_BOL_DETAIL_171705 = _bol_detail_html(
    "https://www.iess.gob.ec/documents/10162/8421754/06_BOLETIN+ESTADISTICO+29+2024.pdf"
)
# No file extension in the real URL -- exercises the icon-based format
# detection instead of a naive ".pdf" suffix check.
_BOL_DETAIL_151612 = _bol_detail_html(
    "https://www.iess.gob.ec/documents/10162/8421754/07_BOLETIN_ESTADISTICO_28_2023"
)
_BOL_DETAIL_50202 = _bol_detail_html(
    "https://www.iess.gob.ec/documents/10162/8421754/31_BOLETIN_ESTADISTICO_01_1978.pdf"
)


@pytest.fixture(autouse=True)
def clear_caches():
    iess_client._boletines_cache.clear()
    iess_client._actuariales_cache.clear()
    iess_client._auditoria_anios_cache.clear()
    iess_client._auditoria_docs_cache.clear()
    yield
    iess_client._boletines_cache.clear()
    iess_client._actuariales_cache.clear()
    iess_client._auditoria_anios_cache.clear()
    iess_client._auditoria_docs_cache.clear()


@pytest.mark.asyncio
async def test_list_boletines_paginates_and_resolves_detail_links(httpx_mock):
    httpx_mock.add_response(url=iess_client._BOL_LIST_URL, html=_BOL_PAGE1_HTML)
    httpx_mock.add_response(url=_BOL_PAGE2_URL, html=_BOL_PAGE2_HTML)
    httpx_mock.add_response(
        url=iess_client._bol_detail_url("171705"), html=_BOL_DETAIL_171705
    )
    httpx_mock.add_response(
        url=iess_client._bol_detail_url("151612"), html=_BOL_DETAIL_151612
    )
    httpx_mock.add_response(
        url=iess_client._bol_detail_url("50202"), html=_BOL_DETAIL_50202
    )

    result = await iess_client.list_boletines()

    assert result["total"] == 3
    assert result["total_en_archivo"] == 3
    by_id = {b["id"]: b for b in result["boletines"]}
    assert by_id["171705"]["anios"] == [2024]
    assert by_id["171705"]["formato"] == "PDF"
    assert by_id["171705"]["url"] == (
        "https://www.iess.gob.ec/documents/10162/8421754/06_BOLETIN+ESTADISTICO+29+2024.pdf"
    )
    # No ".pdf" in the real URL -- must still resolve to PDF via the icon.
    assert by_id["151612"]["formato"] == "PDF"
    assert by_id["151612"]["url"].endswith("07_BOLETIN_ESTADISTICO_28_2023")
    # Confirms page 2 (the 1978 boletín) was actually fetched and merged.
    assert by_id["50202"]["anios"] == [1978]


@pytest.mark.asyncio
async def test_list_boletines_filters_by_anio_and_query(httpx_mock):
    httpx_mock.add_response(url=iess_client._BOL_LIST_URL, html=_BOL_PAGE1_HTML)
    httpx_mock.add_response(url=_BOL_PAGE2_URL, html=_BOL_PAGE2_HTML)
    httpx_mock.add_response(
        url=iess_client._bol_detail_url("171705"), html=_BOL_DETAIL_171705
    )
    httpx_mock.add_response(
        url=iess_client._bol_detail_url("151612"), html=_BOL_DETAIL_151612
    )
    httpx_mock.add_response(
        url=iess_client._bol_detail_url("50202"), html=_BOL_DETAIL_50202
    )

    by_year = await iess_client.list_boletines(anio=1978)
    assert by_year["total"] == 1
    assert by_year["boletines"][0]["id"] == "50202"

    by_query = await iess_client.list_boletines(query="estadistico_28")
    assert by_query["total"] == 1
    assert by_query["boletines"][0]["id"] == "151612"


# --- Estudios Actuariales fixtures --------------------------------------
# The index page links "Estudios/Actuariales YYYY" labels to year pages.
# Two real page layouts are exercised: 2010's static /informacion/ path
# (always .pdf) and 2018's Liferay documents/10162 path, which includes an
# extensionless link (confirmed live: "Seguro Riesgos del Trabajo").

_ACT_INDEX_HTML = """
<html><body>
<div><a href="https://www.iess.gob.ec/es/web/guest/estudios-actuariales-2010" target="_blank" class="enlace" rel="noopener noreferrer">Estudios<br />Actuariales 2010</a></div>
<div><a href="https://www.iess.gob.ec/es/web/guest/estudios-actuariales-2018" target="_blank" class="enlace" rel="noopener noreferrer">Estudios<br />Actuariales 2018</a></div>
</body></html>
"""

_ACT_2010_URL = "https://www.iess.gob.ec/es/web/guest/estudios-actuariales-2010"
_ACT_2010_HTML = """
<html><body>
<h3> Seguro de Invalidez, Vejez y Muerte</h3>
<table><tbody><tr><td><ul><li>
<a href="/informacion/Estudios_Actuariales_2010/Valuacion_Actuarial_del_Seguro_de_Invalidez_Vejez_y_Muerte_2010.pdf">Valuación Actuarial del Seguro de Invalidez, Vejez y Muerte</a>
</li></ul></td></tr></tbody></table>
</body></html>
"""

_ACT_2018_URL = "https://www.iess.gob.ec/es/web/guest/estudios-actuariales-2018"
_ACT_2018_HTML = """
<html><body>
<h3 style="text-align: left;"> Seguro de Riesgos del Trabajo</h3>
<table border="0" cellpadding="10" cellspacing="10" width="650"><tbody><tr><td width="325"><ul><li>
<a href="/documents/10162/14444609/IESS_IVM_estudio_actuarial_011.pdf" target="_blank">Estudio Actuarial del Fondo del Seguro de Riesgos del Trabajo</a>
</li></ul></td><td><ul><li>
<a href="/documents/10162/14444609/Seguro+Riesgos+del+Trabajo" target="_blank">Valuación Actuarial del Seguro de Riesgos del Trabajo</a>
</li></ul></td></tr></tbody></table>
</body></html>
"""


@pytest.mark.asyncio
async def test_list_estudios_actuariales_discovers_years_and_both_layouts(httpx_mock):
    httpx_mock.add_response(url=iess_client._ACT_INDEX_URL, html=_ACT_INDEX_HTML)
    httpx_mock.add_response(url=_ACT_2010_URL, html=_ACT_2010_HTML)
    httpx_mock.add_response(url=_ACT_2018_URL, html=_ACT_2018_HTML)

    result = await iess_client.list_estudios_actuariales()

    assert result["anios_disponibles"] == [2010, 2018]
    assert result["total"] == 3
    doc_2010 = next(d for d in result["documentos"] if d["anio"] == 2010)
    assert doc_2010["formato"] == "PDF"
    assert doc_2010["grupo"] == "Seguro de Invalidez, Vejez y Muerte"
    assert doc_2010["url"] == (
        "https://www.iess.gob.ec/informacion/Estudios_Actuariales_2010/"
        "Valuacion_Actuarial_del_Seguro_de_Invalidez_Vejez_y_Muerte_2010.pdf"
    )

    con_ext = next(
        d for d in result["documentos"] if d["url"].endswith("estudio_actuarial_011.pdf")
    )
    assert con_ext["formato"] == "PDF"
    sin_ext = next(d for d in result["documentos"] if d["url"].endswith("Trabajo"))
    assert sin_ext["formato"] != "PDF"  # assumed, not confirmed by extension
    assert "PDF" in sin_ext["formato"]
    assert sin_ext["grupo"] == "Seguro de Riesgos del Trabajo"


@pytest.mark.asyncio
async def test_list_estudios_actuariales_unknown_anio_raises(httpx_mock):
    httpx_mock.add_response(url=iess_client._ACT_INDEX_URL, html=_ACT_INDEX_HTML)
    httpx_mock.add_response(url=_ACT_2010_URL, html=_ACT_2010_HTML)
    httpx_mock.add_response(url=_ACT_2018_URL, html=_ACT_2018_HTML)

    with pytest.raises(ValueError, match="2013"):
        await iess_client.list_estudios_actuariales(anio=2013)


# --- Informes de Auditoría fixtures --------------------------------------
# The index page's folder table ("Carpeta") links one Liferay folder per
# year, each with a "Número de documentos" column read as total_documentos.
# A year folder's own page lists its documents the same way Boletines
# does, plus an optional file-entry-list-description block.

_AUD_INDEX_HTML = """
<html><body>
<table>
<tr><td>
<a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/58904?_x"><a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/58904?_x"><img align="left" border="0" src="/iess-interno-theme/images/common/folder.png"><strong>2007</strong></a></a>
</td><td headers="prul_col-2">0</td>
<td headers="prul_col-3"> <a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/58904?_x">25</a> </td></tr>
<tr><td>
<a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/25751514?_x"><a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/25751514?_x"><img align="left" border="0" src="/iess-interno-theme/images/common/folder.png"><strong>2024</strong></a></a>
</td><td headers="prul_col-2">0</td>
<td headers="prul_col-3"> <a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/25751514?_x">9</a> </td></tr>
<tr><td>
<a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/40536659?_x"><a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/40536659?_x"><img align="left" border="0" src="/iess-interno-theme/images/common/folder.png"><strong>2026</strong></a></a>
</td><td headers="prul_col-2">0</td>
<td headers="prul_col-3"> <a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/40536659?_x">0</a> </td></tr>
</table>
</body></html>
"""

# 2024's folder (9 documents, fits on one page -- no cur2 pagination).
_AUD_2024_HTML = """
<html><body>
<a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/25751514/140340?_x">
  <span><img class="icon" src="/x/small/_sprite.png"/><span class="taglib-text">DNA7-SySS-0001-2024</span></span>
  <div class="file-entry-list-description"> Examen especial a las fases preparatoria, precontractual. </div>
</a>
</body></html>
"""

_AUD_2024_DOC_DETAIL_HTML = """
<html><body>
<a class="taglib-icon" href="https://www.iess.gob.ec/documents/10162/25751514/DNA7-SySS-0001-2024" target="_blank" title="(Abre una nueva ventana)" >
  <img class="icon" src="/iess-interno-theme/images/file_system/large/pdf.png" alt="Descargar" title="Descargar" />
</a>
</body></html>
"""

# 2007's folder (25 documents -- exceeds the 20/page default, forcing
# get_auditoria_documentos to fetch a second page via cur2).
_AUD_2007_PAGE1_HTML = "".join(
    f"""
    <a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/58904/{100 + i}?_x">
      <span><img class="icon" src="/x/small/_sprite.png"/><span class="taglib-text">2007{i:03d}.pdf</span></span>
    </a>
    """
    for i in range(1, 21)
)
_AUD_2007_PAGE1_HTML = f"<html><body>{_AUD_2007_PAGE1_HTML}</body></html>"

_AUD_2007_PAGE2_URL = (
    "https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/58904"
    "?_110_INSTANCE_vu7F_cur2=2&_110_INSTANCE_vu7F_delta2=20"
)
_AUD_2007_PAGE2_HTML = "".join(
    f"""
    <a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/58904/{200 + i}?_x">
      <span><img class="icon" src="/x/small/_sprite.png"/><span class="taglib-text">2007{20 + i:03d}.pdf</span></span>
    </a>
    """
    for i in range(1, 6)
)
_AUD_2007_PAGE2_HTML = f"<html><body>{_AUD_2007_PAGE2_HTML}</body></html>"


def _aud_doc_detail_html(doc_id: int) -> str:
    return f"""
    <html><body>
    <a class="taglib-icon" href="https://www.iess.gob.ec/documents/10162/58904/2007{doc_id:03d}.pdf" target="_blank" title="(Abre una nueva ventana)" >
      <img class="icon" src="/iess-interno-theme/images/file_system/large/pdf.png" alt="Descargar" title="Descargar" />
    </a>
    </body></html>
    """


@pytest.mark.asyncio
async def test_list_auditoria_anios(httpx_mock):
    httpx_mock.add_response(url=iess_client._AUD_LIST_URL, html=_AUD_INDEX_HTML)

    result = await iess_client.list_auditoria_anios()

    assert result["total_anios"] == 3
    assert result["total_documentos"] == 34  # 25 + 9 + 0
    by_year = {a["anio"]: a for a in result["anios"]}
    assert by_year[2007] == {"anio": 2007, "folder_id": "58904", "total_documentos": 25}
    assert by_year[2024]["folder_id"] == "25751514"
    assert by_year[2026]["total_documentos"] == 0


@pytest.mark.asyncio
async def test_get_auditoria_documentos_single_page_year(httpx_mock):
    httpx_mock.add_response(url=iess_client._AUD_LIST_URL, html=_AUD_INDEX_HTML)
    httpx_mock.add_response(
        url=iess_client._aud_year_folder_url("25751514"), html=_AUD_2024_HTML
    )
    httpx_mock.add_response(
        url=iess_client._aud_year_detail_url("25751514", "140340"),
        html=_AUD_2024_DOC_DETAIL_HTML,
    )

    result = await iess_client.get_auditoria_documentos(2024)

    assert result["total"] == 1
    doc = result["documentos"][0]
    assert doc["titulo"] == "DNA7-SySS-0001-2024"
    assert "Examen especial" in doc["descripcion"]
    assert doc["formato"] == "PDF"
    # No ".pdf" in the real URL -- the whole point of the icon-based check.
    assert doc["url"] == "https://www.iess.gob.ec/documents/10162/25751514/DNA7-SySS-0001-2024"
    assert not doc["url"].lower().endswith(".pdf")


@pytest.mark.asyncio
async def test_get_auditoria_documentos_paginates_within_a_year(httpx_mock):
    httpx_mock.add_response(url=iess_client._AUD_LIST_URL, html=_AUD_INDEX_HTML)
    httpx_mock.add_response(
        url=iess_client._aud_year_folder_url("58904"), html=_AUD_2007_PAGE1_HTML
    )
    httpx_mock.add_response(url=_AUD_2007_PAGE2_URL, html=_AUD_2007_PAGE2_HTML)
    for i in range(1, 26):
        httpx_mock.add_response(
            url=iess_client._aud_year_detail_url("58904", str(100 + i if i <= 20 else 180 + i)),
            html=_aud_doc_detail_html(i),
        )

    result = await iess_client.get_auditoria_documentos(2007)

    assert result["total"] == 25
    assert result["total_en_carpeta"] == 25
    assert all(d["formato"] == "PDF" for d in result["documentos"])


@pytest.mark.asyncio
async def test_get_auditoria_documentos_empty_year_makes_no_extra_requests(httpx_mock):
    httpx_mock.add_response(url=iess_client._AUD_LIST_URL, html=_AUD_INDEX_HTML)

    result = await iess_client.get_auditoria_documentos(2026)

    assert result["total"] == 0
    assert result["documentos"] == []


@pytest.mark.asyncio
async def test_get_auditoria_documentos_unknown_anio_raises(httpx_mock):
    httpx_mock.add_response(url=iess_client._AUD_LIST_URL, html=_AUD_INDEX_HTML)

    with pytest.raises(ValueError, match="2099"):
        await iess_client.get_auditoria_documentos(2099)


@pytest.mark.asyncio
async def test_auditoria_anios_index_paginates_at_exactly_20_folders(httpx_mock):
    # Confirmed live 2026-09-04: exactly 20 year-folders exist today, right
    # at the default page size -- a defensive second-page fetch (cur1=2)
    # guards against a 21st folder (e.g. 2027) going unseen. Build page 1
    # with 20 folders and page 2 with 1 more.
    rows_p1 = "".join(
        f"""
        <a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/{9000 + y}?_x"><a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/{9000 + y}?_x"><img align="left" border="0" src="/iess-interno-theme/images/common/folder.png"><strong>{y}</strong></a></a>
        <td headers="prul_col-3"> <a href="x">1</a> </td>
        """
        for y in range(2007, 2027)
    )
    page1_html = f"<html><body>{rows_p1}</body></html>"

    page2_url = (
        "https://www.iess.gob.ec/es/informes-de-auditoria?p_p_id=110_INSTANCE_vu7F"
        "&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view&p_p_col_id=column-1"
        "&p_p_col_pos=1&p_p_col_count=3&_110_INSTANCE_vu7F_cur1=2"
        "&_110_INSTANCE_vu7F_delta1=20"
    )
    page2_html = """
    <html><body>
    <a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/9027?_x"><a href="https://www.iess.gob.ec/es/informes-de-auditoria/-/document_library_display/vu7F/view/9027?_x"><img align="left" border="0" src="/iess-interno-theme/images/common/folder.png"><strong>2027</strong></a></a>
    <td headers="prul_col-3"> <a href="x">2</a> </td>
    </body></html>
    """

    httpx_mock.add_response(url=iess_client._AUD_LIST_URL, html=page1_html)
    httpx_mock.add_response(url=page2_url, html=page2_html)

    result = await iess_client.list_auditoria_anios()

    assert result["total_anios"] == 21
    assert 2027 in {a["anio"] for a in result["anios"]}

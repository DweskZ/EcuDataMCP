import pytest

from helpers import infomies_client

# Trimmed from real live markup (info.desarrollohumano.gob.ec, confirmed
# 2026-09-03): a Phoca Download category page renders one
# `<div class="pd-filebox">` per file, an `icon-<type>.png` background image
# as the only type signal, and two anchors per file -- the informative one
# (`<a class="" href="...">LABEL</a>`, inside `pd-float`) and a "Descarga"
# button (`<a class="btn btn-success" href="...">Descarga</a>`) pointing at
# the same URL with no useful label.


def _filebox(href: str, label: str, icon: str = "rar") -> str:
    icon_url = f"https://info.desarrollohumano.gob.ec/media/com_phocadownload/images/mime/32/icon-{icon}.png"
    return (
        '<div class="pd-filebox"><div class="pd-filenamebox"><div class="pd-filename">'
        f'<div class="pd-document32" style="background: url(\'{icon_url}\') 0 center no-repeat;">'
        f'<div class="pd-float"><a class="" href="{href}" >{label}</a></div></div></div></div>\n'
        '<div class="pd-buttons"><div class="pd-button-download">'
        f'<a class="btn btn-success" href="{href}" >Descarga</a></div></div><div class="pd-cb"></div></div>'
    )


def _category_page(title: str, fileboxes: str) -> str:
    return f"""
<html><body>
<div id="phoca-dl-category-box" class="pd-category-view"><div class="pd-category">
<h3 class="ph-subheader pd-ctitle" >{title}</h3>{fileboxes}
<div class="pd-cb">&nbsp;</div><div class="pgcenter"></div></div></div>
<div style="text-align:right;color:#ccc;display:block">Powered by <a href="https://www.phoca.cz/phocadownload">Phoca Download</a></div>
</body></html>
"""


_ANC_2026_HTML = _category_page(
    "2026",
    _filebox(
        "/index.php/usuarios-de-inclusion-economica/usuarios-externos-ie/2026-bdd-anc"
        "?download=3285:bases-aseguramiento-no-contributivo-julio",
        "BASES ASEGURAMIENTO NO CONTRIBUTIVO - JULIO",
    )
    + _filebox(
        "/index.php/usuarios-de-inclusion-economica/usuarios-externos-ie/2026-bdd-anc"
        "?download=3268:bases-aseguramiento-no-contributivo-junio",
        "BASES ASEGURAMIENTO NO CONTRIBUTIVO - JUNIO",
    ),
)

_ANC_2024_HTML = _category_page(
    "2024",
    _filebox(
        "/index.php/usuarios-de-inclusion-economica/usuarios-externos-ie/2024-bdd-anc"
        "?download=2944:bases-aseguramiento-no-contributivo-diciembre",
        "BASES ASEGURAMIENTO NO CONTRIBUTIVO - DICIEMBRE",
    ),
)

_EMPTY_YEAR_HTML = """
<html><body>
<div id="phoca-dl-category-box" class="pd-category-view"><div class="pd-category">
<h3 class="ph-subheader pd-ctitle" >2018</h3>
<div class="pd-cb">&nbsp;</div></div></div>
</body></html>
"""

_IS_2019_HTML = _category_page(
    "2019",
    _filebox(
        "/index.php/usuarios-y-unidades-de-inclusion-social/usuarios-externos-is/2019-externos-is-2"
        "?download=1425:usuarios-de-la-unidad-de-atencion-del-siimies-diciembre",
        "USUARIOS DE LA UNIDAD DE ATENCION DEL SIIMIES - DICIEMBRE",
    ),
)

_ZONA1_INDEX_HTML = """
<html><body>
<ul id="menu">
<li><a href="/index.php/zona-1-bz/2017-bz1">2017</a></li>
<li><a href="/index.php/zona-1-bz/2018-bz1">2018</a></li>
<li><a href="/index.php/zona-1-bz/2019-bz1">2019</a></li>
<li><a href="/index.php/zona-1-bz/2020-bz1">2020</a></li>
<li><a href="/index.php/zona-1-bz/2021-bz1">2021</a></li>
</ul>
</body></html>
"""

_ZONA1_2021_HTML = _category_page(
    "2021",
    _filebox(
        "/index.php/zona-1-bz/2021-bz1?download=2201:reporte-zonal-noviembre",
        "REPORTE ZONAL - NOVIEMBRE",
    )
    + _filebox(
        "/index.php/zona-1-bz/2021-bz1?download=2176:reporte-zonal-octubre",
        "REPORTE ZONAL - OCTUBRE",
    ),
)

_ZONA1_2017_HTML = _category_page(
    "2017",
    _filebox(
        "/index.php/zona-1-bz/2017-bz1?download=521:boletin-diciembre",
        "BOLETÍN - DICIEMBRE",
    ),
)

_RBZ_2026_HTML = _category_page(
    "2026",
    _filebox(
        "/index.php/reportes-boletines-zonales/reportes-boletines-zonales-2026"
        "?download=3183:reporte-boletines-zonales",
        "Reporte Boletines Zonales",
        icon="spreadsheet",
    ),
)


@pytest.fixture(autouse=True)
def clear_cache():
    infomies_client._page_cache.clear()
    infomies_client._zona_index_cache.clear()
    yield
    infomies_client._page_cache.clear()
    infomies_client._zona_index_cache.clear()


# --- search_bases_mensuales -------------------------------------------------


@pytest.mark.asyncio
async def test_search_bases_mensuales_anc_specific_year_multiple_months(httpx_mock):
    httpx_mock.add_response(
        url=infomies_client._SERIES["anc"]["anios"][2026], html=_ANC_2026_HTML
    )

    result = await infomies_client.search_bases_mensuales(serie="anc", anio=2026)

    assert result["total"] == 2
    assert result["total_en_pagina"] == 2
    labels = {f["label"] for f in result["archivos"]}
    assert "BASES ASEGURAMIENTO NO CONTRIBUTIVO - JULIO" in labels
    assert all(f["anio"] == 2026 for f in result["archivos"])
    assert all(f["format"] == "RAR" for f in result["archivos"])


@pytest.mark.asyncio
async def test_search_bases_mensuales_closed_year_has_only_december(httpx_mock):
    httpx_mock.add_response(
        url=infomies_client._SERIES["anc"]["anios"][2024], html=_ANC_2024_HTML
    )

    result = await infomies_client.search_bases_mensuales(serie="anc", anio=2024)

    assert result["total"] == 1
    assert "DICIEMBRE" in result["archivos"][0]["label"]


@pytest.mark.asyncio
async def test_search_bases_mensuales_is_series_2019_uses_real_slug_quirk(httpx_mock):
    # Real quirk confirmed live: 2019's actual page is "2019-externos-is-2",
    # not the unsuffixed "2019-externos-is".
    url_2019 = infomies_client._SERIES["is"]["anios"][2019]
    assert url_2019.endswith("2019-externos-is-2")
    httpx_mock.add_response(url=url_2019, html=_IS_2019_HTML)

    result = await infomies_client.search_bases_mensuales(serie="is", anio=2019)

    assert result["total"] == 1
    assert "DICIEMBRE" in result["archivos"][0]["label"]


@pytest.mark.asyncio
async def test_search_bases_mensuales_unknown_serie_raises(httpx_mock):
    with pytest.raises(ValueError, match="Serie"):
        await infomies_client.search_bases_mensuales(serie="bogus")


@pytest.mark.asyncio
async def test_search_bases_mensuales_year_out_of_range_raises(httpx_mock):
    with pytest.raises(ValueError, match="rango"):
        await infomies_client.search_bases_mensuales(serie="anc", anio=2018)


@pytest.mark.asyncio
async def test_search_bases_mensuales_query_filters_accent_insensitive(httpx_mock):
    httpx_mock.add_response(
        url=infomies_client._SERIES["anc"]["anios"][2026], html=_ANC_2026_HTML
    )

    result = await infomies_client.search_bases_mensuales(serie="anc", anio=2026, query="junio")

    assert result["total"] == 1
    assert "JUNIO" in result["archivos"][0]["label"]


@pytest.mark.asyncio
async def test_search_bases_mensuales_empty_page_is_cached(httpx_mock):
    # Unlike most scrapers in this project, an empty result IS cached here
    # (see helpers/infomies_client.py's _fetch_page_items docstring) --
    # confirmed by only registering the mock once and calling twice.
    httpx_mock.add_response(
        url=infomies_client._SERIES["anc"]["anios"][2019], html=_EMPTY_YEAR_HTML
    )

    first = await infomies_client.search_bases_mensuales(serie="anc", anio=2019)
    second = await infomies_client.search_bases_mensuales(serie="anc", anio=2019)

    assert first["total_en_pagina"] == 0
    assert second["total_en_pagina"] == 0


# --- get_boletines_zonales ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_boletines_zonales_discovers_years_and_fetches_specific_one(httpx_mock):
    httpx_mock.add_response(
        url="https://info.desarrollohumano.gob.ec/index.php/zona-1-bz",
        html=_ZONA1_INDEX_HTML,
    )
    httpx_mock.add_response(
        url="https://info.desarrollohumano.gob.ec/index.php/zona-1-bz/2021-bz1",
        html=_ZONA1_2021_HTML,
    )

    result = await infomies_client.get_boletines_zonales(zona="zona-1-bz", anio=2021)

    assert result["total"] == 2
    assert all(f["anio"] == 2021 for f in result["archivos"])
    labels = {f["label"] for f in result["archivos"]}
    assert "REPORTE ZONAL - NOVIEMBRE" in labels


@pytest.mark.asyncio
async def test_get_boletines_zonales_label_wording_varies_by_year(httpx_mock):
    # 2017 uses "BOLETÍN - <mes>" while 2021 uses "REPORTE ZONAL - <mes>" for
    # the same zone -- the parser must not depend on either wording.
    httpx_mock.add_response(
        url="https://info.desarrollohumano.gob.ec/index.php/zona-1-bz",
        html=_ZONA1_INDEX_HTML,
    )
    httpx_mock.add_response(
        url="https://info.desarrollohumano.gob.ec/index.php/zona-1-bz/2017-bz1",
        html=_ZONA1_2017_HTML,
    )

    result = await infomies_client.get_boletines_zonales(zona="zona-1-bz", anio=2017)

    assert result["total"] == 1
    assert "BOLETÍN - DICIEMBRE" in result["archivos"][0]["label"]
    assert result["archivos"][0]["format"] == "RAR"


@pytest.mark.asyncio
async def test_get_boletines_zonales_unknown_zona_raises(httpx_mock):
    with pytest.raises(ValueError, match="Zona"):
        await infomies_client.get_boletines_zonales(zona="zona-99-bz")


@pytest.mark.asyncio
async def test_get_boletines_zonales_year_not_found_raises(httpx_mock):
    httpx_mock.add_response(
        url="https://info.desarrollohumano.gob.ec/index.php/zona-1-bz",
        html=_ZONA1_INDEX_HTML,
    )

    with pytest.raises(ValueError, match="2099"):
        await infomies_client.get_boletines_zonales(zona="zona-1-bz", anio=2099)


def test_list_zonas_returns_nine_fixed_zones():
    zonas = infomies_client.list_zonas()
    assert zonas == [f"zona-{n}-bz" for n in range(1, 10)]


# --- search_reportes_boletines_zonales --------------------------------------


@pytest.mark.asyncio
async def test_search_reportes_boletines_zonales_specific_year(httpx_mock):
    httpx_mock.add_response(
        url=infomies_client._RBZ_ANIOS[2026], html=_RBZ_2026_HTML
    )

    result = await infomies_client.search_reportes_boletines_zonales(anio=2026)

    assert result["total"] == 1
    archivo = result["archivos"][0]
    assert archivo["format"] == "XLSX"
    assert archivo["anio"] == 2026


@pytest.mark.asyncio
async def test_search_reportes_boletines_zonales_year_out_of_range_raises(httpx_mock):
    with pytest.raises(ValueError, match="rango"):
        await infomies_client.search_reportes_boletines_zonales(anio=2019)

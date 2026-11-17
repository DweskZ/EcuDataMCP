from helpers import (
    arcgis_client,
    arcotel_client,
    minedec_client,
    mit_client,
    msp_precios_client,
)

# -- ARCOTEL series ---------------------------------------------------------------


def test_series_key_reads_the_code_and_name():
    assert arcotel_client.series_key("3-1-1-Cuentas-internet-fijos-y-moviles_jun_2026_V2.xlsx") == (
        "3.1.1",
        "Cuentas internet fijos y moviles",
    )
    assert arcotel_client.series_key("15.1.-Listado_Radioaficionados_Mes_Septiembre_2026-1.xlsx") == (
        "15.1",
        "Listado Radioaficionados",
    )
    assert arcotel_client.series_key("Informe_Series_Tel_Fija_Sep2026.xlsx")[0] == "informe_series_tel_fija"
    assert arcotel_client.series_key("RI-1700-1800-Jul-Sep-2026.xlsx") is None


def test_parse_series_media_keeps_the_newest_real_series():
    base = "https://www.arcotel.gob.ec/wp-content/uploads/2026"
    items = [
        {"date": "2026-10-29T10:00:00", "source_url": f"{base}/10/1.1.1-Lineas-activas-por-servicio_y_Densidad_septiembre_2026.xlsx"},
        {"date": "2026-10-05T10:00:00", "source_url": f"{base}/10/1.1.1-Lineas-activas-por-servicio_y_Densidad_agosto_2026.xlsx"},
        {"date": "2025-12-29T10:00:00", "source_url": f"{base}/12/1-Formulario-observaciones-OTECEL.xls"},
        {"date": "2023-12-20T10:00:00", "source_url": f"{base}/12/2.1.181223-OBSERVACIONES-PRI.xlsx"},
        {"date": "2026-10-13T10:00:00", "source_url": f"{base}/10/5.1.1-Usuarios-enlaces-SPT_septiembre_2026.xls"},
    ]

    series = arcotel_client.parse_series_media(items)

    assert [s["codigo"] for s in series] == ["1.1.1", "5.1.1"]
    assert series[0]["url"].endswith("septiembre_2026.xlsx")
    assert series[0]["versiones_vistas"] == 2
    assert series[1]["formato"] == "XLS"


# -- MSP prices -----------------------------------------------------------------


def test_msp_price_releases_carry_their_cutoff_date():
    items = [
        {"date": "2026-10-30T09:00:00", "source_url": "https://www.salud.gob.ec/wp-content/uploads/2026/10/Consolidado-precios-techo-actualizado-2026-10-30.xlsx"},
        {"date": "2021-09-21T09:00:00", "source_url": "https://www.salud.gob.ec/wp-content/uploads/2021/09/Consolidado-precios-techo-actualizado-2021-08-23..xlsx"},
        {"date": "2019-03-28T09:00:00", "source_url": "https://www.salud.gob.ec/wp-content/uploads/2019/03/LISTADO.pdf"},
    ]

    files = msp_precios_client.parse_media(items, "precios_techo")

    assert [f["fecha_corte"] for f in files] == ["2026-10-30", "2021-08-23"]
    assert files[1]["titulo"] == "Consolidado precios techo actualizado 2021 08 23"
    assert {f["tipo"] for f in files} == {"precios_techo"}


# -- MIT road status --------------------------------------------------------------


def test_mit_home_links_the_daily_road_report():
    page = (
        '<a href="http://www.mit.gob.ec/wp-content/uploads/downloads/2017/04/Plan_Estrategico.pdf">x</a>'
        '<div id="banner"><a href="https://www.mit.gob.ec/wp-content/uploads/downloads/2026/11/RVE_VIE06NOV.pdf" target="_self">'
    )

    [report] = mit_client.parse_home(page)

    assert report["fecha"] == "2026-11-06"
    assert report["titulo"] == "Informe Red Vial Estatal 06 NOV 2026"


# -- MINEDEC base-de-datos --------------------------------------------------------

_BASES = """
<a href="//educacion.gob.ec/wp-content/uploads/downloads/2025/04/MINEDUC_RegistrosAdministrativos_2024-2025-Inicio.xlsx"><img></a>
<a href="//educacion.gob.ec/wp-content/uploads/downloads/2025/04/2_MINEDUC_RegistrosAdministrativos_2024-2025Inicio.csv"><img></a>
<a href="https://educacion.gob.ec/wp-content/uploads/downloads/2025/03/3MINEDUC_diccionario_RegistroAdministrativo_2024-2025Inicio.xlsx"><img></a>
<a href="https://educacion.gob.ec/wp-content/uploads/downloads/2019/02/Manual-MAIS-CE.pdf">Manual</a>
<a class="downloadlink" href="https://educacion.gob.ec/wp-content/plugins/download-monitor/download.php?id=3256">1993-1994 (4320)</a>
<a class="downloadlink" href="https://educacion.gob.ec/wp-content/plugins/download-monitor/download.php?id=22597">Conectividad de instituciones educativas fiscales con fines pedag&oacute;gicos (489)</a>
"""


def test_parse_bases_classifies_registers_and_downloads():
    files = minedec_client.parse_bases(_BASES)

    by_tipo = {f["tipo"]: f for f in files}
    assert set(by_tipo) == {"registro_xlsx", "registro_csv", "diccionario", "historico_1993_2007", "tematico"}
    assert by_tipo["registro_csv"]["url"].startswith("https://educacion.gob.ec/")
    assert (by_tipo["registro_csv"]["periodo"], by_tipo["registro_csv"]["corte"]) == ("2024-2025", "Inicio")
    assert by_tipo["tematico"]["titulo"] == "Conectividad de instituciones educativas fiscales con fines pedagógicos"
    assert by_tipo["historico_1993_2007"]["periodo"] == "1993-1994"
    assert not any("MAIS" in f["url"] for f in files)


# -- MSP ArcGIS -------------------------------------------------------------------


async def test_msp_layers_are_listed_with_their_ids():
    result = await arcgis_client.search_capas("msp", query="reproductiva")

    assert [c["capa"] for c in result["capas"]] == ["indicadores_ssr"]
    assert arcgis_client._entry("msp", "establecimientos_rpis")["url"].endswith(
        "/rpis_202501_p/FeatureServer/0"
    )

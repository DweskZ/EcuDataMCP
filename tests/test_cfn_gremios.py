import re
import socket

import pytest

from helpers import gremios_client, sut_powerbi_client


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_DISK_CACHE", "0")

    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    gremios_client._cache.clear()
    yield
    gremios_client._cache.clear()


# -- CFN (Power BI) -----------------------------------------------------------


def test_cfn_is_a_power_bi_fuente_on_its_own_cluster():
    [entry] = sut_powerbi_client.list_indicadores("cfn")

    assert entry["indicador"] == "estadisticas"
    assert entry["base"] == "https://wabi-south-central-us-api.analysis.windows.net"
    assert entry["resource_key"] == "bd2e40e9-243f-4d44-94b9-720388d3a408"


async def test_rows_without_a_descriptor_raise_a_clear_error(httpx_mock):
    from tests.test_sut_powerbi_client import _EXPLORATION_RESPONSE

    [entry] = sut_powerbi_client.list_indicadores("cfn")
    base, key = entry["base"], entry["resource_key"]
    sut_powerbi_client._schema_cache.clear()
    httpx_mock.add_response(
        url=f"{base}/public/reports/{key}/modelsAndExploration", json=_EXPLORATION_RESPONSE
    )
    httpx_mock.add_response(
        url=f"{base}/public/reports/querydata?synchronous=true",
        json={"results": [{"result": {"data": {"dsr": {"DS": []}}}}]},
    )

    try:
        with pytest.raises(ValueError, match="descripción de columnas"):
            await sut_powerbi_client.query_indicador(
                "estadisticas", ["Calendario_.Mes"], limite=5, fuente="cfn"
            )
    finally:
        sut_powerbi_client._schema_cache.clear()


# -- FEDEXPOR ------------------------------------------------------------------

_EXPORDATA = """
<div><a href="https://drive.google.com/file/d/AAA111/view?usp=sharing"><i class="icon"></i></a>
<h3><a href="https://drive.google.com/file/d/AAA111/view?usp=sharing">Expordata Octubre 2026</a></h3></div>
<div><a href="https://drive.google.com/file/d/BBB222/view"></a>
<h3><a href="https://drive.google.com/file/d/BBB222/view">Expordata marzo 2026</a></h3></div>
<div><h3><a href="https://drive.google.com/file/d/CCC333/view">Expordata Especial 2025</a></h3></div>
"""


def test_parse_expordata_dedupes_and_reads_periods():
    items = gremios_client.parse_expordata(_EXPORDATA)

    assert [(i["titulo"], i["periodo"]) for i in items] == [
        ("Expordata Octubre 2026", "2026-10"),
        ("Expordata marzo 2026", "2026-03"),
        ("Expordata Especial 2025", "2025"),
    ]
    assert items[0]["descarga_directa"] == "https://drive.google.com/uc?export=download&id=AAA111"


# -- AEADE ---------------------------------------------------------------------

_VENTAS = """
<div class="sdm_download_title">Boletín de ventas para prensa: ventas de vehículos &#8211; Octubre 2026</div>
<a href="https://www.aeade.net/?sdm_process_download=1&amp;download_id=92031" class="sdm_download">¡Descarga ahora!</a>
<div class="sdm_download_title">Boletín de ventas para prensa: ventas de vehículos Septiembre 2026</div>
<a href="https://www.aeade.net/?sdm_process_download=1&amp;download_id=90669">¡Descarga ahora!</a>
"""
_ANUARIOS = """
<a href="https://www.aeade.net/wp-content/uploads/2026/03/Anuario-Aeade-2025.pdf">2025</a>
<a href="https://www.aeade.net/wp-content/uploads/2025/11/ESTATUTOS-AEADE_2016.pdf">Estatutos</a>
"""


def test_parse_aeade_pairs_titles_with_links_and_skips_statutes():
    ventas = gremios_client.parse_aeade_ventas(_VENTAS)
    anuarios = gremios_client.parse_aeade_anuarios(_ANUARIOS)

    assert [(v["periodo"], v["url"]) for v in ventas] == [
        ("2026-10", "https://www.aeade.net/?sdm_process_download=1&download_id=92031"),
        ("2026-09", "https://www.aeade.net/?sdm_process_download=1&download_id=90669"),
    ]
    assert ventas[0]["titulo"].endswith("– Octubre 2026")
    assert [(a["titulo"], a["periodo"], a["tipo"]) for a in anuarios] == [
        ("Anuario Aeade 2025", "2025", "anuario")
    ]


async def test_search_aeade_combines_both_pages_and_filters(httpx_mock):
    httpx_mock.add_response(url=re.compile(r".*boletines-de-prensa-venta-de-vehiculos/"), text=_VENTAS)
    httpx_mock.add_response(url=re.compile(r".*aeade\.net/anuario/"), text=_ANUARIOS)

    everything = await gremios_client.search_aeade()
    anuarios = await gremios_client.search_aeade("anuario")

    assert len(everything["archivos"]) == 3
    assert [a["tipo"] for a in anuarios["archivos"]] == ["anuario"]

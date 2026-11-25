import socket
import time

import httpx
import pytest

from helpers import sni_client
from tools import search_archivos as sa


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_DISK_CACHE", "0")

    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    sni_client._cache.clear()
    yield
    sni_client._cache.clear()


_PAGE = """<!DOCTYPE html><html><body><main>
<table id="tablepress-9" class="tablepress"><tr><td>ignored</td></tr></table>
<table id="tablepress-1" class="tablepress tablepress-id-1">
<thead>
<tr class="row-1 odd">
	<th class="column-1">Nro</th><th class="column-2">Sector</th><th class="column-3">Entidad ejecutora</th><th class="column-4">Entidad evaluadora</th><th class="column-5">Tipo</th><th class="column-6">Intervención</th><th class="column-7">Año</th><th class="column-8">Objetivo</th><th class="column-9">Archivo</th>
</tr>
</thead>
<tbody class="row-hover">
<tr class="row-2 even">
	<td class="column-1">2</td><td class="column-2">Educación</td><td class="column-3">Ministerio de Educación.</td><td class="column-4">Secretaría Nacional de Planificación</td><td class="column-5">Diseño<br />
Implementación<br />
Resultados<br />
</td><td class="column-6">Programa de Alimentación Escolar &amp; Textos</td><td class="column-7">2024</td><td class="column-8">Evaluar el diseño<br />
y los resultados del programa.</td><td class="column-9"><a href="/wp-content/uploads/2024/05/Informe_PAE.pdf" target="_blank">Descargar</a></td>
</tr>
<tr class="row-3 odd">
	<td class="column-1">1</td><td class="column-2">Desarrollo Productivo</td><td class="column-3">Ministerio de Agricultura</td><td class="column-4">Presidencia</td><td class="column-5">Resultados</td><td class="column-6">Estrategia Nacional Agropecuaria</td><td class="column-7">2024</td><td class="column-8">Medir resultados.</td><td class="column-9"><a href="/wp-content/uploads/2024/01/Informe_ENA.pdf">Descargar</a></td>
</tr>
<tr class="row-4 even">
	<td class="column-1">50</td><td class="column-2">Social</td><td class="column-3">MIES</td><td class="column-4">SENPLADES</td><td class="column-5">Impacto</td><td class="column-6">Bono de Desarrollo Humano</td><td class="column-7">2017</td><td class="column-8">Estimar el impacto.</td><td class="column-9"><a href="https://sni.gob.ec/wp-content/uploads/2017/03/BDH.rar">Descargar</a></td>
</tr>
<tr class="row-5 odd">
	<td class="column-1">51</td><td class="column-2">Social</td><td class="column-3">MIES</td><td class="column-4">SENPLADES</td><td class="column-5">Impacto</td><td class="column-6">Informe sin archivo</td><td class="column-7">2016</td><td class="column-8">Sin enlace.</td><td class="column-9"></td>
</tr>
</tbody>
</table>
</main></body></html>"""


def test_parse_reads_every_column_and_resolves_the_link():
    entries = sni_client.parse_evaluaciones(_PAGE.encode())

    pae = next(e for e in entries if e["nro"] == 2)
    assert pae["titulo"] == "Programa de Alimentación Escolar & Textos"
    assert pae["url"] == "https://www.sni.gob.ec/wp-content/uploads/2024/05/Informe_PAE.pdf"
    assert pae["formato"] == "PDF"
    assert pae["anio"] == 2024
    assert pae["categoria"] == "Educación"
    assert pae["entidad_ejecutora"] == "Ministerio de Educación."
    assert pae["tipo"] == "Diseño Implementación Resultados"
    assert pae["objetivo"] == "Evaluar el diseño y los resultados del programa."


def test_parse_drops_rows_without_a_report_and_keeps_absolute_links():
    entries = sni_client.parse_evaluaciones(_PAGE.encode())

    assert "Informe sin archivo" not in [e["titulo"] for e in entries]
    bono = next(e for e in entries if e["nro"] == 50)
    assert bono["url"] == "https://sni.gob.ec/wp-content/uploads/2017/03/BDH.rar"
    assert bono["formato"] == "RAR"


def test_parse_orders_by_year_descending_then_row_number():
    entries = sni_client.parse_evaluaciones(_PAGE.encode())

    assert [(e["anio"], e["nro"]) for e in entries] == [(2024, 1), (2024, 2), (2017, 50)]


def test_parse_without_the_table_returns_nothing():
    assert sni_client.parse_evaluaciones(b"<html><body>Mantenimiento</body></html>") == []


async def test_search_ignores_accents_and_needs_every_word(httpx_mock):
    httpx_mock.add_response(url=sni_client._PAGE_URL, content=_PAGE.encode(), is_reusable=True)

    by_sector = await sni_client.search_evaluaciones("educacion")
    spread = await sni_client.search_evaluaciones("alimentacion 2024 diseno")
    one_word_missing = await sni_client.search_evaluaciones("educacion 2017")
    everything = await sni_client.search_evaluaciones()

    assert [e["nro"] for e in by_sector["archivos"]] == [2]
    assert [e["nro"] for e in spread["archivos"]] == [2]
    assert one_word_missing["archivos"] == []
    assert len(everything["archivos"]) == 3
    assert everything["url_fuente"] == sni_client._PAGE_URL


async def test_formato_filter_works_through_search_archivos(httpx_mock):
    httpx_mock.add_response(url=sni_client._PAGE_URL, content=_PAGE.encode(), is_reusable=True)

    pdf = await sa._search("sni_evaluaciones", "", limit=50, offset=0, formato="pdf")
    rar = await sa._search("sni_evaluaciones", "", limit=50, offset=0, formato="RAR")

    assert pdf["total"] == 2
    assert [a["titulo"] for a in rar["archivos"]] == ["Bono de Desarrollo Humano"]
    assert rar["archivos"][0]["anio"] == 2017


async def test_catalog_is_served_stale_when_the_site_goes_down(httpx_mock):
    httpx_mock.add_response(url=sni_client._PAGE_URL, content=_PAGE.encode())
    await sni_client.search_evaluaciones()

    # Expire the cached copy (tests/test_cache.py sets entries the same way), then
    # make the host refuse the next fetch.
    _, entries = sni_client._cache._store["evaluaciones"]
    sni_client._cache._store["evaluaciones"] = (time.time() - 1, entries)
    httpx_mock.add_exception(httpx.ConnectError("down"), url=sni_client._PAGE_URL)

    result = await sni_client.search_evaluaciones("bono")

    assert [e["nro"] for e in result["archivos"]] == [50]

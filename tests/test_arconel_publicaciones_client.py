import json

import pytest

from helpers import arconel_publicaciones_client as client

_DM = "https://arconel.gob.ec/wp-content/plugins/download-monitor/download.php"
_UP = "https://arconel.gob.ec/wp-content/uploads/downloads"

# Excerpts of the live pages (checked 2026-10-26).
_ESTADISTICA = f"""
<ul class="ul-downloads">
<li class="li-gray1" id="cat-142" >
  <a style="display: block;"><span class="ico">+</span>2025</a>
  <ul><li class="li-gray4"><span class="titulo">Estadística 2025</span>
    <a href="{_DM}?id=1274&force=0" title="Ver Estadística 2025" class="ver">ver</a>
    <a href="{_DM}?id=1274&force=1" title="Descargar Estadística 2025">descarga</a>
    <a href="{_DM}?id=1285&amp;force=1" title="Descargar Atlas del Sector Eléctrico 2025">d</a>
  </li></ul>
</li>
<li class="li-gray1" id="cat-90" >
  <a style="display: block;"><span class="ico">+</span>2024</a>
  <ul><li class="li-gray4">
    <a href="{_DM}?id=439&force=1" title="Descargar Estadística 2024">descarga</a>
  </li></ul>
</li>
</ul>
"""
_TARIFAS = f"""
<div class="ar-year"><span>AÑO 2026</span>
  <a href="{_UP}/2026/01/Resolucion-ARCONEL-021-25.pdf">Resolución Nro. ARCONEL-021/25</a>
</div>
<div class="ar-year"><span>AÑO 2025</span>
  <a href="{_UP}/2025/01/Pliego-2025.pdf"><strong>Pliego Tarifario 2025</strong></a>
  <a href="{_UP}/2025/01/Pliego-2025.pdf">Pliego Tarifario 2025 (duplicado)</a>
</div>
"""
_BALANCE = f'<a href="{_UP}/2026/10/BNEE_julio_2026.xls">Balance Nacional Julio 2026</a>'
_TEMAS_POST = {
    "content": {
        "rendered": """<script>const TEMAS = [
    {
      title: &quot;Generación y Transmisión&quot;,
      items: [
        {
          type: &quot;reg&quot;,
          code: &quot;ARCONEL-001/24&quot;,
          title: &quot;Código de Conexión&quot;,
          href: &quot;https://arconel.gob.ec/wp-content/uploads/downloads/2026/07/Reg-001-24.pdf&quot;
        },
      ]
    },
    {
      title: &quot;Régimen Económico&quot;,
      items: [
        {
          type: &quot;res&quot;,
          code: &quot;ARCONEL-012/25&quot;,
          title: &quot;Proyectos de Desarrollo Territorial&quot;,
          href: &quot;https://arconel.gob.ec/wp-content/uploads/downloads/2025/09/Res-012-25.pdf&quot;
        }
      ]
    }
];</script>"""
    }
}


def _seccion(nombre: str) -> dict:
    return next(s for s in client._SECCIONES if s["seccion"] == nombre)


@pytest.fixture(autouse=True)
def clear_cache():
    client._cache.clear()
    yield
    client._cache.clear()


def test_list_secciones_uses_public_pages():
    secciones = {s["seccion"]: s["url"] for s in client.list_secciones()}

    assert list(secciones) == ["estadistica", "mapas", "balances", "tarifas", "regulaciones"]
    assert secciones["regulaciones"].endswith(
        "/regulaciones-vigentes-del-sector-electrico-ecuatoriano/"
    )


async def test_estadistica_library_groups_by_year(httpx_mock):
    httpx_mock.add_response(url=_seccion("estadistica")["paginas"][0], html=_ESTADISTICA)

    result = await client.get_seccion_archivos("estadistica")

    assert [(a["grupo"], a["titulo"]) for a in result["archivos"]] == [
        ("2025", "Estadística 2025"),
        ("2025", "Atlas del Sector Eléctrico 2025"),
        ("2024", "Estadística 2024"),
    ]
    assert result["archivos"][1]["url"] == f"{_DM}?id=1285&force=1"


async def test_tarifas_take_year_headers_and_dedupe(httpx_mock):
    paginas = _seccion("tarifas")["paginas"]
    httpx_mock.add_response(url=paginas[0], html=_TARIFAS)
    for url in paginas[1:]:
        httpx_mock.add_response(url=url, html="<p>Sin archivos.</p>")

    archivos = (await client.get_seccion_archivos("tarifas"))["archivos"]

    assert [(a["periodo"], a["titulo"], a["formato"]) for a in archivos] == [
        ("2026", "Resolución Nro. ARCONEL-021/25", "PDF"),
        ("2025", "Pliego Tarifario 2025", "PDF"),
    ]
    assert archivos[0]["grupo"] == "Servicio público de energía eléctrica (SPEE)"


async def test_balances_list_workbooks(httpx_mock):
    paginas = _seccion("balances")["paginas"]
    httpx_mock.add_response(url=paginas[0], html=_BALANCE)
    for url in paginas[1:]:
        httpx_mock.add_response(url=url, html="")

    archivos = (await client.get_seccion_archivos("balances"))["archivos"]

    assert archivos == [
        {
            "titulo": "Balance Nacional Julio 2026",
            "url": f"{_UP}/2026/10/BNEE_julio_2026.xls",
            "formato": "XLS",
            "grupo": "Balance nacional de energía eléctrica",
            "periodo": None,
        }
    ]


async def test_regulaciones_read_temas_array(httpx_mock):
    httpx_mock.add_response(
        url=_seccion("regulaciones")["paginas"][0], text=json.dumps(_TEMAS_POST)
    )

    archivos = (await client.get_seccion_archivos("regulaciones"))["archivos"]

    assert [(a["grupo"], a["tipo"], a["titulo"]) for a in archivos] == [
        ("Generación y Transmisión", "Regulación", "ARCONEL-001/24 — Código de Conexión"),
        ("Régimen Económico", "Resolución", "ARCONEL-012/25 — Proyectos de Desarrollo Territorial"),
    ]


async def test_regulaciones_without_temas_raises(httpx_mock):
    httpx_mock.add_response(
        url=_seccion("regulaciones")["paginas"][0],
        text=json.dumps({"content": {"rendered": "<p>Página rediseñada.</p>"}}),
    )

    with pytest.raises(ValueError, match="TEMAS"):
        await client.get_seccion_archivos("regulaciones")


async def test_unknown_section_lists_valid_ones():
    with pytest.raises(ValueError, match="estadistica, mapas"):
        await client.get_seccion_archivos("presupuesto")

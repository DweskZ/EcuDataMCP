import pytest
from mcp.server.mcpserver import MCPServer

from helpers import cortes_programados_client as client
from tools.cortes import register_cortes_tools


def _post(post_id: int, title: str, body: str, categories: list[int] | None = None) -> dict:
    return {
        "id": post_id,
        "date": "2026-10-15T10:00:00",
        "link": f"https://example.gob.ec/aviso-{post_id}/",
        "title": {"rendered": title},
        "content": {"rendered": body},
        "categories": categories or [7],
    }


# Bodies as the sites render them (checked live 2026-10-26).
_EMELNORTE = [
    _post(
        10989,
        "Suspensión de Servicio Eléctrico sábado 17 de octubre de 2026",
        "<p>[vc_row][vc_column]</p><p>SUSPENSIÓN POR ELECTRIFICACIÓN MALCHINGUÍ</p>"
        "<p><strong>FECHAS:</strong><br/> sábado 17 de octubre de 2026</p>"
        "<p><strong>HORA:</strong><br/> DE 08:00 A 10:00</p>"
        "<p><strong>SECTORES AFECTADOS:</strong></p>"
        "<p>Sector Cruz Loma, parroquia Malchinguí.</p>"
        "<p>Pedimos disculpas por las molestias ocasionadas.</p>"
        "<p>DIRECCIÓN DE DISTRIBUCIÓN</p>",
    ),
    _post(
        10099,
        "Suspensión de Servicio Eléctrico lunes 15 de junio de 2026",
        "<p>SUSPENSIÓN POR EXTENSION DE RED</p><p>FECHAS</p><p>: lunes 15 de junio de 2026</p>"
        "<p>HORA:</p><p>DE 09H00 A 12H00</p><p>SECTORES AFECTADOS:</p><p>San Jose de Cacho</p>",
    ),
    _post(
        11013,
        "Suspensión de Servicio Eléctrico sábado 24 de octubre de 2026",
        '<p>Mantenimiento de la Subestación Cotacachi</p><a href="https://example.gob.ec/a.png">'
        '<img src="https://example.gob.ec/a-620x540.png"/></a>',
    ),
]
_GALAPAGOS = [
    _post(
        32190,
        "Mantenimientos Programados San Cristóbal, 27 de octubre de 2026.",
        "<p>Fecha:<br> Martes, 27 de octubre de 2026</p><p>De 09H00 a 12H00</p>"
        "<p>Sector: El Chino.</p><p>Instituciones afectadas: Jocotoco.</p>"
        "<p>Desmontaje de transformador.</p><p>De 14H30 a 16H00</p>"
        "<p>Sectores:</p><p>Barrio Los Cactus.</p><p>Poda.</p>",
        [77],
    ),
    _post(
        31726,
        "Mantenimientos Programados Santa Cruz, 15 de junio de 2026.",
        "<p>Fecha de inicio: Lunes,</p><p>15/06/2026</p><p>Hora de Inicio:</p><p>17h00</p>"
        "<p>Fecha de fin : Martes,</p><p>16/06/2026</p><p>Hora de Fin:</p><p>02h00</p>"
        "<p>Sector:</p><p>Baltra</p><p>Mantenimiento de transformador de elevación.</p>",
        [78],
    ),
    _post(
        31979,
        "Mantenimientos Programados Isabela, 14 de agosto de 2026.",
        "<p>Viernes 14/08/2026</p><p>08H00 a 12H00</p><p>SECTOR:</p><p>Barrio Pedregal 2</p>"
        "<p>Reubicación de postes.</p>",
        [79],
    ),
]
_EEASA = """
<div class="card-body">
  <h5 class="card-title mb-2"><strong>Fecha:</strong> martes, 27 - octubre - 2026</h5>
  <p class="card-text mb-1"><strong>Horario:</strong> 09:00 a 14:00</p>
  <p class="card-text mb-1"><strong>Sector:</strong> PROVINCIA: PASTAZA, SECTORES: ü\tArajuno
ü\tShikulin</p>
  <p class="card-text mb-1"><strong>Motivo:</strong> CAMBIO ESTRUCTURAS MV</p>
</div>
<div class="card-body">
  <h5 class="card-title mb-2"><strong>Fecha:</strong> martes, 27 - octubre - 2026</h5>
  <p class="card-text mb-1"><strong>Horario:</strong> 10:00 a 13:00</p>
  <p class="card-text mb-1"><strong>Sector:</strong> QUISAPINCHA - TUNGURAHUA</p>
</div>
"""


@pytest.fixture(autouse=True)
def clear_cache():
    client._cache.clear()
    yield
    client._cache.clear()


@pytest.fixture
def feeds(httpx_mock):
    httpx_mock.add_response(
        url=client._FUENTES["emelnorte"]["url"], json=_EMELNORTE, is_optional=True
    )
    httpx_mock.add_response(
        url=client._FUENTES["elecgalapagos"]["url"], json=_GALAPAGOS, is_optional=True
    )
    httpx_mock.add_response(url=client._FUENTES["eeasa"]["url"], html=_EEASA, is_optional=True)
    return httpx_mock


async def test_emelnorte_text_notice(feeds):
    result = await client.get_horarios("emelnorte", "10989")

    assert result["filas"] == [
        {
            "pagina": 1,
            "fecha_texto": "sábado 17 de octubre de 2026",
            "horario": ["08:00-10:00"],
            "sectores": "Sector Cruz Loma, parroquia Malchinguí.",
            "motivo": "SUSPENSIÓN POR ELECTRIFICACIÓN MALCHINGUÍ",
        }
    ]


async def test_emelnorte_colon_on_next_line(feeds):
    fila = (await client.get_horarios("emelnorte", "10099"))["filas"][0]

    assert fila["fecha_texto"] == "lunes 15 de junio de 2026"
    assert fila["horario"] == ["09:00-12:00"]


async def test_emelnorte_image_only_notice_returns_links(feeds):
    result = await client.get_horarios("emelnorte", "11013")

    assert result["filas"] == []
    assert result["imagenes"] == ["https://example.gob.ec/a.png"]
    assert "solo como imagen" in result["nota"]


async def test_elecgalapagos_one_row_per_job(feeds):
    filas = (await client.get_horarios("elecgalapagos", "32190"))["filas"]

    assert [(f["horario"], f["sectores"], f["zona"]) for f in filas] == [
        (["09:00-12:00"], "El Chino.", "San Cristóbal"),
        (["14:30-16:00"], "Barrio Los Cactus.", "San Cristóbal"),
    ]
    assert filas[0]["instituciones"] == "Jocotoco."
    assert filas[1]["motivo"] == "Poda."


async def test_elecgalapagos_overnight_job(feeds):
    fila = (await client.get_horarios("elecgalapagos", "31726"))["filas"][0]

    assert fila["fecha_texto"] == "Lunes, 15/06/2026"
    assert fila["fecha_fin"] == "Martes, 16/06/2026"
    assert fila["horario"] == ["17:00-02:00"]
    assert fila["sectores"] == "Baltra"
    assert "_inicio" not in fila


async def test_elecgalapagos_unlabeled_layout(feeds):
    fila = (await client.get_horarios("elecgalapagos", "31979"))["filas"][0]

    assert (fila["fecha_texto"], fila["horario"], fila["sectores"], fila["zona"]) == (
        "Viernes 14/08/2026",
        ["08:00-12:00"],
        "Barrio Pedregal 2",
        "Isabela",
    )


async def test_eeasa_cards_and_query(feeds):
    result = await client.get_horarios("eeasa", "vigentes", query="tungurahua")

    assert result["total_en_archivo"] == 2
    assert [f["horario"] for f in result["filas"]] == [["10:00-13:00"]]

    todas = (await client.get_horarios("eeasa", "vigentes"))["filas"]
    assert todas[0]["sectores"] == "PROVINCIA: PASTAZA, SECTORES: Arajuno Shikulin"
    assert todas[0]["motivo"] == "CAMBIO ESTRUCTURAS MV"


async def test_search_filters_and_rejects_unknown_post(feeds):
    result = await client.search("emelnorte", query="malchingui")
    assert [a["archivo"] for a in result["archivos"]] == ["10989"]
    assert result["total_en_archivo"] == 3

    with pytest.raises(ValueError, match="no está entre los 3"):
        await client.get_horarios("emelnorte", "1")


async def test_tool_text_shows_motive_without_placeholder(feeds):
    server = MCPServer("test")
    register_cortes_tools(server)

    got = await server.call_tool(
        "get_cortes_horarios", {"distribuidora": "eeasa", "archivo": "vigentes"}
    )

    text = got.content[0].text
    assert "Motivo: CAMBIO ESTRUCTURAS MV" in text
    assert "ubicación no reconocida" not in text

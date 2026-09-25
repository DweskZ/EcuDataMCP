import pytest

from helpers import gobec_client


@pytest.mark.asyncio
async def test_list_regulaciones(httpx_mock):
    httpx_mock.add_response(
        url="https://www.gob.ec/api/v1/regulaciones?page=0",
        json=[
            {
                "regulacion_id": "5051",
                "regulacion": "Reglamento demo",
                "tipo": "Acuerdo ministerial",
                "descripcion": "Texto sobre protección",
            }
        ],
    )
    items = await gobec_client.list_regulaciones(page=0)
    assert len(items) == 1
    assert items[0]["regulacion_id"] == "5051"


@pytest.mark.asyncio
async def test_find_regulaciones(httpx_mock):
    httpx_mock.add_response(
        url="https://www.gob.ec/api/v1/regulaciones?page=0",
        json=[
            {
                "regulacion_id": "1",
                "regulacion": "Ley de datos personales",
                "descripcion": "Protección de datos",
                "tipo": "Ley",
            },
            {
                "regulacion_id": "2",
                "regulacion": "Reglamento de tránsito",
                "descripcion": "Vehículos",
                "tipo": "Reglamento",
            },
        ],
    )
    httpx_mock.add_response(
        url="https://www.gob.ec/api/v1/regulaciones?page=1",
        json=[],
    )
    matches = await gobec_client.find_regulaciones("datos personales", max_pages=2)
    assert len(matches) == 1
    assert matches[0]["regulacion_id"] == "1"


@pytest.mark.asyncio
async def test_get_tramite_estadisticas(httpx_mock):
    httpx_mock.add_response(
        url="https://www.gob.ec/api/v1/tramites-transparencia/11752",
        json=[
            {
                "tramite_transparencia_id": "420887",
                "tramite_id": "11752",
                "ano": "2026",
                "mes": "07",
                "atenciones": "253729",
                "quejas": "6",
                "modificado": '<time datetime="2026-08-11T11:22:05-05:00">2026-08-11T11:22:05-0500</time>\n',
            }
        ],
    )
    rows = await gobec_client.get_tramite_estadisticas("11752")
    assert len(rows) == 1
    assert rows[0]["ano"] == "2026"
    assert rows[0]["atenciones"] == "253729"


@pytest.mark.asyncio
async def test_get_tramite_estadisticas_missing_returns_empty_list(httpx_mock):
    httpx_mock.add_response(
        url="https://www.gob.ec/api/v1/tramites-transparencia/999999",
        json=[],
    )
    rows = await gobec_client.get_tramite_estadisticas("999999")
    assert rows == []


@pytest.mark.asyncio
async def test_list_regulaciones_raises_on_empty_body(httpx_mock):
    # Confirmed live 2026-09-19: gob.ec answers a blocked/bot-suspected
    # request with HTTP 200 and an empty body instead of a 4xx, so
    # resp.json() raises json.JSONDecodeError. _fetch_json must turn that
    # into a message naming the likely cause, not let the bare
    # JSONDecodeError text reach the caller.
    httpx_mock.add_response(
        url="https://www.gob.ec/api/v1/regulaciones?page=0",
        text="",
    )
    with pytest.raises(RuntimeError, match="respuesta vacía o no válida"):
        await gobec_client.list_regulaciones(page=0)

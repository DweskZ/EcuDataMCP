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

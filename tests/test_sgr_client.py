import pytest

from helpers import sgr_client
from helpers.cache import TtlCache


@pytest.mark.asyncio
async def test_list_risk_events_filters(monkeypatch):
    sample = [
        {
            "attributes": {
                "OBJECTID": 1,
                "Provincia": "PICHINCHA",
                "Canton": "QUITO",
                "Parroquia": "CENTRO",
                "Evento": "Deslizamiento",
                "EstadoDelEvento": "Seguimiento",
                "FechaDelEvento": "2025-01-02",
                "DescripcionGeneralDeEvento": "Deslizamiento por lluvias",
            }
        },
        {
            "attributes": {
                "OBJECTID": 2,
                "Provincia": "GUAYAS",
                "Canton": "GUAYAQUIL",
                "Parroquia": "X",
                "Evento": "Inundación",
                "EstadoDelEvento": "Cierre",
                "FechaDelEvento": "2025-01-01",
                "DescripcionGeneralDeEvento": "Inundación urbana",
            }
        },
    ]

    async def fake_layer_url() -> str:
        return "https://example.test/COE2/MapServer/0"

    async def fake_get_json(url: str, params=None):
        assert url.endswith("/query")
        return {"features": sample}

    monkeypatch.setattr(sgr_client, "_coe2_layer_url", fake_layer_url)
    monkeypatch.setattr(sgr_client, "_get_json", fake_get_json)
    monkeypatch.setattr(sgr_client, "_events_cache", TtlCache(ttl_seconds=60))

    result = await sgr_client.list_risk_events(provincia="Pichincha", estado="Seguimiento")
    assert result["total"] == 1
    assert result["events"][0]["Canton"] == "QUITO"

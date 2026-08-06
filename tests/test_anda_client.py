import pytest

from helpers import anda_client


@pytest.mark.asyncio
async def test_search_catalog(httpx_mock):
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/api/catalog?ps=10&sk=empleo",
        json={
            "result": {
                "found": "1",
                "rows": [
                    {
                        "id": "1319",
                        "idno": "ECU-INEC-EMPLEO-2025",
                        "title": "Encuesta de Empleo 2025",
                        "year_start": "2025",
                        "authoring_entity": "INEC",
                        "form_model": "direct",
                        "url": "https://anda.inec.gob.ec/anda5/index.php/catalog/1319",
                    }
                ],
            }
        },
    )
    result = await anda_client.search_catalog(query="empleo", limit=10)
    assert result["found"] == "1"
    assert result["rows"][0]["idno"] == "ECU-INEC-EMPLEO-2025"


@pytest.mark.asyncio
async def test_search_catalog_no_query(httpx_mock):
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/api/catalog?ps=5",
        json={"result": {"found": "437", "rows": []}},
    )
    result = await anda_client.search_catalog(limit=5)
    assert result["found"] == "437"


def test_has_microdata_direct():
    assert anda_client.has_microdata({"form_model": "direct"}) is True


def test_has_microdata_aggregate_only():
    assert anda_client.has_microdata({"form_model": "data_na"}) is False


def test_has_microdata_from_detail_field():
    assert anda_client.has_microdata({"data_access_type": "direct"}) is True
    assert anda_client.has_microdata({"data_access_type": "data_na"}) is False


@pytest.mark.asyncio
async def test_get_survey(httpx_mock):
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/api/catalog/ECU-INEC-EMPLEO-2025",
        json={
            "status": "success",
            "dataset": {
                "id": "1319",
                "idno": "ECU-INEC-EMPLEO-2025",
                "title": "Encuesta de Empleo 2025",
                "data_access_type": "direct",
                "varcount": "150",
            },
        },
    )
    dataset = await anda_client.get_survey("ECU-INEC-EMPLEO-2025")
    assert dataset["id"] == "1319"
    assert dataset["varcount"] == "150"


@pytest.mark.asyncio
async def test_get_survey_not_found(httpx_mock):
    httpx_mock.add_response(
        url="https://anda.inec.gob.ec/anda5/index.php/api/catalog/NOPE",
        status_code=400,
        json={"status": "failed", "message": "IDNO-NOT-FOUND"},
    )
    with pytest.raises(ValueError, match="No se encontró"):
        await anda_client.get_survey("NOPE")

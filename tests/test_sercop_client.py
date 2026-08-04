import pytest

from helpers import sercop_client


@pytest.mark.asyncio
async def test_search_contracts_success(httpx_mock):
    httpx_mock.add_response(
        url="https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds?year=2024&search=agua&page=1",
        json={
            "total": 1,
            "page": "1",
            "pages": 1,
            "data": [
                {
                    "ocid": "ocds-5wno2w-demo",
                    "title": "001-DEMO",
                    "buyerName": "GAD DEMO",
                    "description": "Obra de agua",
                }
            ],
        },
    )
    result = await sercop_client.search_contracts(search="agua", year=2024, page=1)
    assert result["total"] == 1
    assert result["data"][0]["ocid"] == "ocds-5wno2w-demo"


@pytest.mark.asyncio
async def test_search_contracts_rejects_short_query():
    with pytest.raises(ValueError):
        await sercop_client.search_contracts(search="ab", year=2024)


@pytest.mark.asyncio
async def test_get_contract_record(httpx_mock):
    ocid = "ocds-5wno2w-demo"
    httpx_mock.add_response(
        url=f"https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/record?ocid={ocid}",
        json={
            "records": [
                {
                    "ocid": ocid,
                    "releases": [
                        {
                            "buyer": {"name": "GAD DEMO"},
                            "tender": {"title": "Demo", "status": "complete"},
                            "tag": ["tender", "award"],
                        }
                    ],
                }
            ]
        },
    )
    result = await sercop_client.get_contract_record(ocid)
    assert result["records"][0]["ocid"] == ocid

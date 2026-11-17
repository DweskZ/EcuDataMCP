import httpx
import pytest

from helpers import http_client, sercop_client
from helpers.cache import TtlCache


@pytest.fixture(autouse=True)
def _reset_sercop_state():
    http_client.reset_cooldowns()
    sercop_client.sercop_search_cache = TtlCache(ttl_seconds=60)
    sercop_client._negative_cache = TtlCache(ttl_seconds=60)
    yield
    http_client.reset_cooldowns()


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
async def test_search_contracts_rate_limit(httpx_mock, monkeypatch):
    monkeypatch.setattr(sercop_client, "_MAX_RETRIES", 2)

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(http_client.asyncio, "sleep", _no_sleep)

    url = (
        "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds"
        "?year=2024&search=agua&page=1"
    )
    httpx_mock.add_response(url=url, status_code=429)
    httpx_mock.add_response(url=url, status_code=429)

    with pytest.raises(sercop_client.SercopRateLimitError):
        await sercop_client.search_contracts(search="agua", year=2024, page=1)


@pytest.mark.asyncio
async def test_search_contracts_names_regional_block_on_connect_error(
    httpx_mock, monkeypatch
):
    monkeypatch.setattr(sercop_client, "_MAX_RETRIES", 1)

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(http_client.asyncio, "sleep", _no_sleep)

    httpx_mock.add_exception(httpx.ConnectError("All connection attempts failed"))

    with pytest.raises(RuntimeError, match="compraspublicas.gob.ec"):
        await sercop_client.search_contracts(search="agua", year=2024, page=1)


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


@pytest.mark.asyncio
async def test_search_contracts_fallback_year(httpx_mock):
    httpx_mock.add_response(
        url="https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds?year=2026&search=agua&page=1",
        json={"total": 0, "page": "1", "pages": 0, "data": []},
    )
    httpx_mock.add_response(
        url="https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds?year=2025&search=agua&page=1",
        json={
            "total": 1,
            "page": "1",
            "pages": 1,
            "data": [{"ocid": "ocds-2025", "title": "Agua 2025"}],
        },
    )
    result = await sercop_client.search_contracts(
        search="agua", year=2026, page=1, fallback_years=1
    )
    assert result["_resolved_year"] == 2025
    assert result["data"][0]["ocid"] == "ocds-2025"


@pytest.mark.asyncio
async def test_search_rejects_redirect_to_html_without_caching(httpx_mock):
    url = "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/search_ocds?year=2024&search=agua&page=1"
    target = "https://datosabiertos.compraspublicas.gob.ec/ProcesoContratacion/app/webroot/compras/index.php"
    httpx_mock.add_response(url=url, status_code=302, headers={"Location": target})
    httpx_mock.add_response(url=target, html="<html>Portal de compras</html>")
    httpx_mock.add_response(url=url, json={"total": 0, "page": "1", "pages": 0, "data": []})

    with pytest.raises(sercop_client.SercopResponseError, match="redirección.*JSON"):
        await sercop_client.search_contracts("agua", 2024, fallback_years=1)
    result = await sercop_client.search_contracts("agua", 2024)
    assert result["data"] == []
    assert len(httpx_mock.get_requests()) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], {}, {"data": None}, {"data": ["invalid"]}])
async def test_search_rejects_unexpected_schema(httpx_mock, payload):
    httpx_mock.add_response(json=payload)
    with pytest.raises(sercop_client.SercopResponseError, match="estructura inesperada"):
        await sercop_client.search_contracts("agua", 2024, fallback_years=1)
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_search_rejects_invalid_json(httpx_mock):
    httpx_mock.add_response(content=b"{broken", headers={"content-type": "application/json"})
    with pytest.raises(sercop_client.SercopResponseError, match="JSON inválido"):
        await sercop_client.search_contracts("agua", 2024)


@pytest.mark.asyncio
async def test_search_reports_http_error(httpx_mock):
    httpx_mock.add_response(status_code=404)
    with pytest.raises(sercop_client.SercopResponseError, match="HTTP 404"):
        await sercop_client.search_contracts("agua", 2024)


@pytest.mark.asyncio
async def test_record_rejects_unexpected_schema(httpx_mock):
    httpx_mock.add_response(json={"error": "unavailable"})
    with pytest.raises(sercop_client.SercopResponseError, match="estructura inesperada"):
        await sercop_client.get_contract_record("ocds-5wno2w-demo")

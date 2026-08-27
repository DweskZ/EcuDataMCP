import httpx
import pytest

from helpers import ckan_client


async def test_connect_timeout_names_the_host(httpx_mock):
    url = "https://www.datosabiertos.gob.ec/api/3/action/package_search"
    httpx_mock.add_exception(httpx.ConnectTimeout("", request=httpx.Request("GET", url)))

    with pytest.raises(RuntimeError, match="www.datosabiertos.gob.ec"):
        await ckan_client._fetch_json(url)


async def test_connect_error_names_the_host(httpx_mock):
    url = "https://www.datosabiertos.gob.ec/api/3/action/package_search"
    httpx_mock.add_exception(httpx.ConnectError("", request=httpx.Request("GET", url)))

    with pytest.raises(RuntimeError, match="www.datosabiertos.gob.ec"):
        await ckan_client._fetch_json(url)


async def test_http_status_error_is_not_wrapped(httpx_mock):
    url = "https://www.datosabiertos.gob.ec/api/3/action/package_search"
    httpx_mock.add_response(url=url, status_code=500, content=b"internal error")

    with pytest.raises(httpx.HTTPStatusError):
        await ckan_client._fetch_json(url)

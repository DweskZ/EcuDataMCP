import httpx
import pytest

from helpers import ckan_client
from helpers.cache import categories_cache


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


# -- source routing (nacional vs cuenca) -------------------------------------


def test_ckan_url_defaults_to_nacional_portal():
    assert ckan_client._ckan_url("package_search") == (
        "https://www.datosabiertos.gob.ec/api/3/action/package_search"
    )


def test_ckan_url_routes_to_cuenca_portal():
    assert ckan_client._ckan_url("package_search", source="cuenca") == (
        "https://cuencaendatos.cuenca.gob.ec/api/3/action/package_search"
    )


def test_ckan_url_rejects_unknown_source():
    with pytest.raises(ValueError, match="source inválido"):
        ckan_client._ckan_url("package_search", source="otro")


def test_site_url_matches_source():
    assert ckan_client.site_url() == "https://www.datosabiertos.gob.ec/"
    assert ckan_client.site_url("cuenca") == "https://cuencaendatos.cuenca.gob.ec/"


async def test_search_datasets_hits_cuenca_endpoint(httpx_mock):
    url = "https://cuencaendatos.cuenca.gob.ec/api/3/action/package_search"
    httpx_mock.add_response(
        url=httpx.URL(url, params={"q": "actas", "rows": 20, "start": 0}),
        json={"success": True, "result": {"count": 1, "results": []}},
    )

    result = await ckan_client.search_datasets(query="actas", source="cuenca")

    assert result["count"] == 1


async def test_get_dataset_hits_cuenca_endpoint(httpx_mock):
    url = "https://cuencaendatos.cuenca.gob.ec/api/3/action/package_show"
    httpx_mock.add_response(
        url=httpx.URL(url, params={"id": "silla-vacia"}),
        json={"success": True, "result": {"id": "silla-vacia"}},
    )

    result = await ckan_client.get_dataset("silla-vacia", source="cuenca")

    assert result["id"] == "silla-vacia"


async def test_list_groups_caches_nacional_and_cuenca_separately(httpx_mock):
    categories_cache.clear()
    nacional_url = "https://www.datosabiertos.gob.ec/api/3/action/group_list"
    cuenca_url = "https://cuencaendatos.cuenca.gob.ec/api/3/action/group_list"
    httpx_mock.add_response(
        url=httpx.URL(nacional_url, params={"all_fields": "true"}),
        json={"success": True, "result": [{"name": "salud"}]},
    )
    httpx_mock.add_response(
        url=httpx.URL(cuenca_url, params={"all_fields": "true"}),
        json={"success": True, "result": [{"name": "movilidad"}]},
    )

    nacional_groups = await ckan_client.list_groups()
    cuenca_groups = await ckan_client.list_groups(source="cuenca")

    assert nacional_groups == [{"name": "salud"}]
    assert cuenca_groups == [{"name": "movilidad"}]

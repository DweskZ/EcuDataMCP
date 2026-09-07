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


# -- get_organization (full package list, not organization_show's capped one) -


async def test_get_organization_fetches_full_package_list_via_search(httpx_mock):
    # organization_show's own `packages` field is capped by the portal's
    # per-page default (confirmed live: 10 of 94 for a real organization) --
    # this must come from package_search instead, not organization_show.
    httpx_mock.add_response(
        url="https://www.datosabiertos.gob.ec/api/3/action/organization_show?id=test-org",
        json={
            "success": True,
            "result": {
                "name": "test-org",
                "title": "Test Org",
                "package_count": 2,
                "packages": [{"name": "stale-truncated-entry"}],
            },
        },
    )
    httpx_mock.add_response(
        url=(
            "https://www.datosabiertos.gob.ec/api/3/action/package_search"
            "?fq=organization%3Atest-org&rows=1000&sort=metadata_modified+desc"
        ),
        json={
            "success": True,
            "result": {
                "count": 2,
                "results": [
                    {"name": "dataset-a", "metadata_modified": "2026-01-01"},
                    {"name": "dataset-b", "metadata_modified": "2020-01-01"},
                ],
            },
        },
    )

    org = await ckan_client.get_organization("test-org")

    assert org["package_count"] == 2
    assert [p["name"] for p in org["packages"]] == ["dataset-a", "dataset-b"]


async def test_get_organization_skips_package_search_when_not_requested(httpx_mock):
    httpx_mock.add_response(
        url="https://www.datosabiertos.gob.ec/api/3/action/organization_show?id=test-org",
        json={"success": True, "result": {"name": "test-org", "package_count": 2}},
    )

    org = await ckan_client.get_organization("test-org", include_datasets=False)

    assert "packages" not in org


# -- source routing (nacional vs cuenca) -------------------------------------


def test_ckan_url_defaults_to_nacional_portal():
    assert ckan_client._ckan_url("package_search") == (
        "https://www.datosabiertos.gob.ec/api/3/action/package_search"
    )


def test_ckan_url_routes_to_cuenca_portal():
    assert ckan_client._ckan_url("package_search", source="cuenca") == (
        "https://cuencaendatos.cuenca.gob.ec/api/3/action/package_search"
    )


def test_ckan_url_routes_to_latacunga_portal():
    assert ckan_client._ckan_url("package_search", source="latacunga") == (
        "https://datosabiertos.latacunga.gob.ec/api/3/action/package_search"
    )


def test_ckan_url_rejects_unknown_source():
    with pytest.raises(ValueError, match="source inválido"):
        ckan_client._ckan_url("package_search", source="otro")


def test_site_url_matches_source():
    assert ckan_client.site_url() == "https://www.datosabiertos.gob.ec/"
    assert ckan_client.site_url("cuenca") == "https://cuencaendatos.cuenca.gob.ec/"
    assert (
        ckan_client.site_url("latacunga")
        == "https://datosabiertos.latacunga.gob.ec/"
    )


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


async def test_search_datasets_hits_latacunga_endpoint(httpx_mock):
    url = "https://datosabiertos.latacunga.gob.ec/api/3/action/package_search"
    httpx_mock.add_response(
        url=httpx.URL(url, params={"q": "catastro", "rows": 20, "start": 0}),
        json={"success": True, "result": {"count": 1, "results": []}},
    )

    result = await ckan_client.search_datasets(query="catastro", source="latacunga")

    assert result["count"] == 1


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

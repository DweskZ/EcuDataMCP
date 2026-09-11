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


# -- source="iadb" (data.iadb.org) --


async def test_search_datasets_hits_iadb_endpoint(httpx_mock):
    url = "https://data.iadb.org/api/3/action/package_search"
    httpx_mock.add_response(
        url=httpx.URL(url, params={"q": "Latin Macro Watch", "rows": 20, "start": 0}),
        json={"success": True, "result": {"count": 1, "results": []}},
    )

    result = await ckan_client.search_datasets(query="Latin Macro Watch", source="iadb")

    assert result["count"] == 1


def test_resolve_source_invalid_mentions_iadb():
    with pytest.raises(ValueError, match="iadb"):
        ckan_client._resolve_source("no-existe")


# -- IADB's multilingual title/description/notes fields --
# data.iadb.org's CKAN instance (unlike the national/municipal portals)
# returns these as a {"es": ..., "en": ...} dict at the package level —
# confirmed live 2026-09-10 against package_show. Every existing tool's
# text rendering expects a plain string, so _fetch_json collapses these to
# one language before returning.


def test_localize_prefers_spanish():
    value = {"en": "English title", "es": "Título en español"}
    assert ckan_client._localize(value) == "Título en español"


def test_localize_falls_back_to_english_then_first_value():
    assert ckan_client._localize({"en": "English only"}) == "English only"
    assert ckan_client._localize({"fr": "Seulement en français"}) == "Seulement en français"


def test_localize_is_a_noop_for_plain_strings():
    assert ckan_client._localize("Ya es un string") == "Ya es un string"
    assert ckan_client._localize(None) is None


async def test_package_search_localizes_multilingual_titles(httpx_mock):
    url = "https://data.iadb.org/api/3/action/package_search"
    httpx_mock.add_response(
        url=httpx.URL(url, params={"q": "macro", "rows": 20, "start": 0}),
        json={
            "success": True,
            "result": {
                "count": 1,
                "results": [
                    {
                        "name": "latin-macro-watch-dataset",
                        "title": {"en": "Latin Macro Watch", "es": "Latin Macro Watch (ES)"},
                        "notes": {"en": "English notes", "es": "Notas en español"},
                        "organization": {"title": {"en": "IDB", "es": "BID"}},
                        "resources": [],
                    }
                ],
            },
        },
    )

    result = await ckan_client.search_datasets(query="macro", source="iadb")

    pkg = result["results"][0]
    assert pkg["title"] == "Latin Macro Watch (ES)"
    assert pkg["notes"] == "Notas en español"
    assert pkg["organization"]["title"] == "BID"


async def test_get_dataset_localizes_a_single_package(httpx_mock):
    url = "https://data.iadb.org/api/3/action/package_show"
    httpx_mock.add_response(
        url=httpx.URL(url, params={"id": "latin-macro-watch-dataset"}),
        json={
            "success": True,
            "result": {
                "name": "latin-macro-watch-dataset",
                "title": {"en": "Latin Macro Watch", "es": "Latin Macro Watch (ES)"},
                "resources": [{"name": "Unemployment rate", "format": "CSV"}],
            },
        },
    )

    result = await ckan_client.get_dataset("latin-macro-watch-dataset", source="iadb")

    assert result["title"] == "Latin Macro Watch (ES)"
    # Resource-level fields are already plain strings on the real portal —
    # untouched either way.
    assert result["resources"][0]["name"] == "Unemployment rate"


async def test_search_datasets_does_not_touch_plain_string_titles_on_national_portal(httpx_mock):
    url = "https://www.datosabiertos.gob.ec/api/3/action/package_search"
    httpx_mock.add_response(
        url=httpx.URL(url, params={"q": "salud", "rows": 20, "start": 0}),
        json={
            "success": True,
            "result": {
                "count": 1,
                "results": [{"name": "salud-dataset", "title": "Dataset de Salud"}],
            },
        },
    )

    result = await ckan_client.search_datasets(query="salud")

    assert result["results"][0]["title"] == "Dataset de Salud"

import asyncio
import re

import pytest

from helpers import ant_client, ckan_client, inec_client

_WP_POSTS = re.compile(r"https://www\.ecuadorencifras\.gob\.ec/wp-json/wp/v2/posts.*")
_WP_CATS = re.compile(
    r"https://www\.ecuadorencifras\.gob\.ec/wp-json/wp/v2/categories.*"
)
_CKAN_ORG = re.compile(r".*/api/3/action/package_search.*fq=organization.*")
_CKAN_SEARCH = re.compile(r".*/api/3/action/package_search.*")


def _post(post_id: int, title: str, date: str) -> dict:
    return {
        "id": post_id,
        "link": f"https://www.ecuadorencifras.gob.ec/p{post_id}/",
        "date": f"{date}T10:00:00",
        "modified": f"{date}T10:00:00",
        "title": {"rendered": title},
        "categories": [],
    }


def _pkg(name: str, title: str, org: str = "inec") -> dict:
    return {
        "name": name,
        "title": title,
        "organization": {"name": org},
        "metadata_modified": "2022-05-12T15:40:57",
        "resources": [{"name": "r", "format": "CSV", "url": f"https://x/{name}.csv"}],
    }


@pytest.fixture(autouse=True)
def clear_caches():
    for cache in (
        ant_client._cache,
        inec_client._categories_cache,
        inec_client._publicacion_files_cache,
    ):
        cache.clear()
    yield


def _mock_inec(httpx_mock) -> None:
    httpx_mock.add_response(
        url=_WP_CATS, json=[], headers={"X-WP-TotalPages": "1"}, is_reusable=True
    )
    httpx_mock.add_response(
        url=_WP_POSTS,
        json=[
            _post(2, "Siniestros de Tránsito IV trimestre 2025", "2026-05-28"),
            _post(1, "Siniestros de Tránsito III trimestre 2023", "2024-02-28"),
            _post(3, "Censo Penitenciario 2022", "2023-05-18"),
        ],
        is_reusable=True,
    )


@pytest.mark.asyncio
async def test_search_combines_inec_and_ckan(httpx_mock):
    _mock_inec(httpx_mock)
    httpx_mock.add_response(
        url=_CKAN_ORG,
        json={
            "success": True,
            "result": {
                "results": [_pkg("excesos-velocidad", "Excesos de velocidad", "antec")]
            },
        },
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=_CKAN_SEARCH,
        json={
            "success": True,
            "result": {
                "results": [
                    _pkg(
                        "fallecidos-sppat",
                        "Fallecidos por accidentes de tránsito SPPAT",
                    ),
                    _pkg("proyectos", "PROYECTOS DE INVERSIÓN", "cte"),
                ]
            },
        },
        is_reusable=True,
    )
    result = await ant_client.search_siniestros(con_archivos=0)
    titles = [p["titulo"] for p in result["publicaciones_inec"]]
    assert titles == [
        "Siniestros de Tránsito IV trimestre 2025",
        "Siniestros de Tránsito III trimestre 2023",
    ]
    ids = [d["id"] for d in result["datasets_ckan"]]
    assert "fallecidos-sppat" in ids
    assert "excesos-velocidad" in ids
    assert "proyectos" not in ids
    assert result["avisos"] == []


@pytest.mark.asyncio
async def test_year_filter(httpx_mock):
    _mock_inec(httpx_mock)
    httpx_mock.add_response(
        url=_CKAN_SEARCH,
        json={"success": True, "result": {"results": []}},
        is_reusable=True,
    )
    result = await ant_client.search_siniestros(anio=2023, con_archivos=0)
    assert [p["id"] for p in result["publicaciones_inec"]] == [1]


@pytest.mark.asyncio
async def test_ckan_failure_keeps_inec_results(httpx_mock):
    _mock_inec(httpx_mock)
    httpx_mock.add_response(url=_CKAN_SEARCH, status_code=500, is_reusable=True)
    result = await ant_client.search_siniestros(con_archivos=0)
    assert len(result["publicaciones_inec"]) == 2
    assert result["datasets_ckan"] == []
    assert any("CKAN" in a for a in result["avisos"])


@pytest.mark.asyncio
async def test_failed_attached_files_lookup_is_reported_but_others_survive(
    httpx_mock, monkeypatch
):
    _mock_inec(httpx_mock)
    httpx_mock.add_response(
        url=_CKAN_SEARCH,
        json={"success": True, "result": {"results": []}},
        is_reusable=True,
    )

    async def fake_files(post_id):
        if post_id == 2:
            raise ValueError("sin conexión")
        return {"archivos": [{"label": "Tabulados", "url": "https://x/t.xlsx", "format": "XLSX"}]}

    monkeypatch.setattr(inec_client, "get_publicacion_files", fake_files)

    result = await ant_client.search_siniestros(con_archivos=2)

    by_id = {p["id"]: p for p in result["publicaciones_inec"]}
    assert "archivos" not in by_id[2]
    assert by_id[1]["archivos"][0]["label"] == "Tabulados"
    assert any("publicación 2" in a and "sin conexión" in a for a in result["avisos"])


@pytest.mark.asyncio
async def test_inec_and_ckan_queries_run_concurrently_within_the_bound(monkeypatch):
    stats = {"now": 0, "max": 0}

    async def tracked(result):
        stats["now"] += 1
        stats["max"] = max(stats["max"], stats["now"])
        await asyncio.sleep(0.02)
        stats["now"] -= 1
        return result

    async def fake_inec(query, limit=20, offset=0):
        return await tracked({"publicaciones": []})

    async def fake_search(query="", rows=20, **kwargs):
        return await tracked({"results": []})

    async def fake_filter(fq, rows=50, **kwargs):
        return await tracked({"results": []})

    monkeypatch.setattr(inec_client, "search_publicaciones", fake_inec)
    monkeypatch.setattr(ckan_client, "search_datasets", fake_search)
    monkeypatch.setattr(ckan_client, "search_datasets_by_filter", fake_filter)

    result = await ant_client.search_siniestros(con_archivos=0)

    assert result["avisos"] == []
    # 2 INEC + 3 CKAN calls, in flight together but never beyond the bound.
    assert 2 < stats["max"] <= ant_client._CONCURRENCY


@pytest.mark.asyncio
async def test_ant_org_filter_goes_through_the_public_ckan_wrapper(httpx_mock):
    httpx_mock.add_response(
        url=_CKAN_ORG,
        json={"success": True, "result": {"results": [_pkg("licencias", "Licencias", "antec")]}},
    )

    result = await ckan_client.search_datasets_by_filter("organization:antec", rows=50)

    assert result["results"][0]["name"] == "licencias"
    request = httpx_mock.get_requests()[0]
    assert request.url.params["fq"] == "organization:antec"
    assert request.url.params["rows"] == "50"

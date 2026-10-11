import re

import pytest

from helpers import ant_client, inec_client

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

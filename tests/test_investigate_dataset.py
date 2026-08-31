import json

from mcp.server.fastmcp import FastMCP

import tools.investigate_dataset as investigate_dataset_module
from helpers import ckan_client
from tools.investigate_dataset import register_investigate_dataset_tool


def _make_tool():
    mcp = FastMCP("test")
    register_investigate_dataset_tool(mcp)
    return mcp._tool_manager.get_tool("investigate_dataset").fn


_DATASET_WITH_PERIODIC_CSVS = {
    "id": "ds1",
    "name": "precios-cacao",
    "title": "Precios de cacao",
    "resources": [
        {
            "id": "res1",
            "name": "precios_2024_enero.csv",
            "format": "CSV",
            "url": "https://x/precios_2024_enero.csv",
        },
        {
            "id": "res2",
            "name": "precios_2024_febrero.csv",
            "format": "CSV",
            "url": "https://x/precios_2024_febrero.csv",
        },
        {
            "id": "res3",
            "name": "precios_2024_marzo.csv",
            "format": "CSV",
            "url": "https://x/precios_2024_marzo.csv",
        },
    ],
}


async def test_investigate_dataset_previews_first_csv_resource(monkeypatch):
    async def fake_search_datasets(query, rows=1, source="nacional", session=None):
        return {"count": 1, "results": [{"id": "ds1", "name": "precios-cacao"}]}

    async def fake_get_dataset(dataset_id, source="nacional", session=None):
        assert dataset_id == "ds1"
        return _DATASET_WITH_PERIODIC_CSVS

    async def fake_preview_csv(url, max_rows=20, session=None):
        assert url == "https://x/precios_2024_enero.csv"
        return {
            "headers": ["producto", "precio"],
            "rows": [["cacao", "120.5"]],
            "total_rows_in_preview": 1,
            "format": "csv",
        }

    monkeypatch.setattr(ckan_client, "search_datasets", fake_search_datasets)
    monkeypatch.setattr(ckan_client, "get_dataset", fake_get_dataset)
    monkeypatch.setitem(
        investigate_dataset_module._PREVIEW_DISPATCH, "CSV", fake_preview_csv
    )

    fn = _make_tool()
    text = await fn(query="cacao", format="json")
    data = json.loads(text)

    assert data["dataset"]["title"] == "Precios de cacao"
    assert data["resource"]["id"] == "res1"
    assert data["headers"] == ["producto", "precio"]
    assert data["rows"] == [["cacao", "120.5"]]
    # 3 resources sharing a "precios_2024_#.csv" name template -> periodic
    assert data["posible_serie_periodica"] is True


async def test_investigate_dataset_no_search_results(monkeypatch):
    async def fake_search_datasets(query, rows=1, source="nacional", session=None):
        return {"count": 0, "results": []}

    monkeypatch.setattr(ckan_client, "search_datasets", fake_search_datasets)

    fn = _make_tool()
    text = await fn(query="zzz", format="json")
    data = json.loads(text)

    assert data["error"] == "sin_resultados"


async def test_investigate_dataset_skips_unpreviewable_resource(monkeypatch):
    async def fake_search_datasets(query, rows=1, source="nacional", session=None):
        return {"count": 1, "results": [{"id": "ds2", "name": "solo-rar"}]}

    async def fake_get_dataset(dataset_id, source="nacional", session=None):
        return {
            "id": "ds2",
            "name": "solo-rar",
            "title": "Solo RAR",
            "resources": [
                {
                    "id": "res1",
                    "name": "archivo.rar",
                    "format": "RAR",
                    "url": "https://x/archivo.rar",
                }
            ],
        }

    monkeypatch.setattr(ckan_client, "search_datasets", fake_search_datasets)
    monkeypatch.setattr(ckan_client, "get_dataset", fake_get_dataset)

    fn = _make_tool()
    text = await fn(query="archivo", format="json")
    data = json.loads(text)

    assert data["error"] == "sin_recurso_previsualizable"
    assert data["recursos"][0]["id"] == "res1"

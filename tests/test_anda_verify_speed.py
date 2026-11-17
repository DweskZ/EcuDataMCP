"""verify_access: bounded concurrency, early exit, persistent cache, auto mode."""

import asyncio
import json

import pytest
from mcp.server.mcpserver import MCPServer

from helpers import anda_client
from tools.search_anda import register_search_anda_tool

BASE = "https://anda.inec.gob.ec/anda5/index.php"


def _row(i, form_model="direct", changed="2020-01-01"):
    return {
        "id": str(i),
        "idno": f"ECU-{i}",
        "title": f"Encuesta {i}",
        "year_start": "2020",
        "authoring_entity": "INEC",
        "form_model": form_model,
        "changed": changed,
        "url": f"{BASE}/catalog/{i}",
    }


def _direct(sid):
    return {
        "tipo_acceso": "directo",
        "archivos": [{"filename": "a.zip", "url": f"{BASE}/catalog/{sid}/download/1"}],
        "enlaces_externos": [],
        "nota": None,
    }


@pytest.fixture(autouse=True)
def _clean_caches():
    anda_client._access_cache.clear()
    anda_client._access_store.clear()
    yield
    anda_client._access_cache.clear()
    anda_client._access_store.clear()


def _patch_probe(monkeypatch, delay=0.0):
    state = {"calls": [], "active": 0, "peak": 0}

    async def fake(survey_id, session=None):
        state["calls"].append(survey_id)
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(delay)
        state["active"] -= 1
        return _direct(survey_id)

    monkeypatch.setattr(anda_client, "get_microdata_access", fake)
    return state


@pytest.mark.asyncio
async def test_probes_run_concurrently_but_never_above_the_bound(monkeypatch):
    state = _patch_probe(monkeypatch, delay=0.02)
    rows = [_row(i) for i in range(1, 21)]

    out = await anda_client.verify_access(rows, concurrency=8)

    assert len(out) == 20
    assert 2 <= state["peak"] <= 8
    assert state["peak"] == 8


@pytest.mark.asyncio
async def test_default_concurrency_is_eight(monkeypatch):
    state = _patch_probe(monkeypatch, delay=0.02)
    await anda_client.verify_access([_row(i) for i in range(1, 30)])
    assert state["peak"] == anda_client.VERIFY_CONCURRENCY == 8


@pytest.mark.asyncio
async def test_a_failed_probe_maps_to_none_without_failing_the_rest(monkeypatch):
    async def fake(survey_id, session=None):
        if survey_id == "2":
            raise RuntimeError("boom")
        return _direct(survey_id)

    monkeypatch.setattr(anda_client, "get_microdata_access", fake)
    out = await anda_client.verify_access([_row(1), _row(2), _row(3)])
    assert out["2"] is None
    assert out["1"]["tipo_acceso"] == "directo"
    assert anda_client._access_cache.get("2") is None


@pytest.mark.asyncio
async def test_public_form_model_skips_the_probe(monkeypatch):
    state = _patch_probe(monkeypatch)
    out = await anda_client.verify_access([_row(351, "public"), _row(1)])
    assert out["351"]["tipo_acceso"] == "registro"
    assert state["calls"] == ["1"]


@pytest.mark.asyncio
async def test_direct_form_model_is_never_trusted(monkeypatch):
    """CPV 2022 is `direct` in the catalog yet only links to another site."""
    state = _patch_probe(monkeypatch)
    await anda_client.verify_access([_row(1085, "direct")])
    assert state["calls"] == ["1085"]


@pytest.mark.asyncio
async def test_memory_cache_avoids_a_second_probe(monkeypatch):
    state = _patch_probe(monkeypatch)
    rows = [_row(1), _row(2)]
    await anda_client.verify_access(rows)
    await anda_client.verify_access(rows)
    assert sorted(state["calls"]) == ["1", "2"]


@pytest.mark.asyncio
async def test_persistent_store_survives_a_new_session(monkeypatch, tmp_path):
    monkeypatch.setenv("ECUADOR_MCP_DISK_CACHE", "1")
    monkeypatch.setenv("ECUADOR_MCP_DATA_DIR", str(tmp_path))
    state = _patch_probe(monkeypatch)
    rows = [_row(1)]
    await anda_client.verify_access(rows)
    saved = json.loads((tmp_path / "cache" / "anda_access.json").read_text())
    assert any(k.startswith('"1|2020-01-01"') for k in saved)

    # New session: memory is gone, a fresh store object re-reads the disk file.
    anda_client._access_cache.clear()
    monkeypatch.setattr(
        anda_client, "_access_store", anda_client.TtlCache(7 * 86400.0, 2048, persist="anda_access")
    )
    out = await anda_client.verify_access(rows)

    assert state["calls"] == ["1"]
    assert out["1"]["tipo_acceso"] == "directo"


@pytest.mark.asyncio
async def test_a_changed_catalog_timestamp_invalidates_the_stored_answer(monkeypatch):
    state = _patch_probe(monkeypatch)
    await anda_client.verify_access([_row(1, changed="2020-01-01")])
    anda_client._access_cache.clear()
    await anda_client.verify_access([_row(1, changed="2021-06-01")])
    assert state["calls"] == ["1", "1"]


@pytest.mark.asyncio
async def test_top_limits_the_probes(monkeypatch):
    state = _patch_probe(monkeypatch)
    out = await anda_client.verify_access([_row(i) for i in range(1, 8)], top=3)
    assert sorted(state["calls"]) == ["1", "2", "3"]
    assert set(out) == {"1", "2", "3"}


def _search_tool():
    mcp = MCPServer("test")
    register_search_anda_tool(mcp)
    return mcp._tool_manager.get_tool("search_anda").fn


def _mock_catalog(httpx_mock, n):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog?ps=50", json={"result": {"found": str(n), "rows": [_row(i) for i in range(1, n + 1)]}}
    )


@pytest.mark.asyncio
async def test_auto_verifies_only_the_top_and_flags_the_rest(httpx_mock, monkeypatch):
    state = _patch_probe(monkeypatch)
    _mock_catalog(httpx_mock, 14)

    res = (await _search_tool()(limit=50, format="json")).structured_content

    assert len(state["calls"]) == 10
    kinds = [r["tipo_acceso"] for r in res["results"]]
    assert kinds[:10] == ["directo"] * 10
    assert kinds[10:] == ["desconocido"] * 4
    assert "nota_acceso" not in res["results"][0]
    assert "verificar_acceso" in res["results"][12]["nota_acceso"]
    assert "4 más" in res["aviso_verificacion"]


@pytest.mark.asyncio
async def test_true_verifies_everything_and_false_nothing(httpx_mock, monkeypatch):
    state = _patch_probe(monkeypatch)
    _mock_catalog(httpx_mock, 12)
    _mock_catalog(httpx_mock, 12)

    full = (await _search_tool()(limit=50, verificar_acceso=True, format="json")).structured_content
    assert len(state["calls"]) == 12
    assert {r["tipo_acceso"] for r in full["results"]} == {"directo"}
    assert "aviso_verificacion" not in full

    state["calls"].clear()
    off = (await _search_tool()(limit=50, verificar_acceso=False, format="json")).structured_content
    assert state["calls"] == []
    assert {r["tipo_acceso"] for r in off["results"]} == {"desconocido"}
    assert "aviso_verificacion" not in off

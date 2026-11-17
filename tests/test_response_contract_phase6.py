import asyncio
import json
import time

import pytest

from helpers import cache as cache_module
from helpers.cache import TtlCache
from helpers.format_out import (
    cap_response,
    derive_pagination,
    render_structured,
    resource_links,
)
from helpers.response_contract import stale_responses


@pytest.fixture(autouse=True)
def memory_only(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_DISK_CACHE", "0")


# -- uniform byte cap ---------------------------------------------------------


def test_cap_response_trims_the_biggest_list_and_says_so(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_MAX_RESPONSE_BYTES", "2000")
    payload = {"query": "x", "tags": ["a"], "rows": [{"v": "y" * 100} for _ in range(50)]}

    capped = cap_response(payload)

    kept = capped["metadatos"]["truncado"]["filas_devueltas"]
    assert 1 <= kept < 50
    assert len(capped["rows"]) == kept
    assert capped["metadatos"]["truncado"]["filas_omitidas"] == 50 - kept
    # cap_rows measures the payload before adding its own truncado note.
    body = {k: v for k, v in capped.items() if k != "metadatos"}
    assert len(json.dumps(body, ensure_ascii=False)) <= 2000
    assert capped["tags"] == ["a"]


def test_cap_response_leaves_small_payloads_and_tool_caps_alone(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_MAX_RESPONSE_BYTES", "50")
    small = {"rows": [1]}
    already = {"rows": list(range(500)), "metadatos": {"truncado": {"filas_devueltas": 500}}}

    assert cap_response(small) is small
    assert cap_response(already) is already


# -- pagination ---------------------------------------------------------------


def test_offset_pagination_points_at_the_next_offset():
    payload = {"offset": 20, "total": 45, "members": [{}] * 20}

    page = derive_pagination(payload)

    assert page == {
        "estilo": "offset",
        "actual": 20,
        "devueltas": 20,
        "total": 45,
        "hay_mas": True,
        "siguiente": {"offset": 40},
    }


def test_page_pagination_from_total_and_page_size():
    last = derive_pagination({"page": 3, "page_size": 10, "total": 30, "results": [{}] * 10})
    middle = derive_pagination({"page": 2, "pages": 5, "results": [{}] * 10})

    assert last["hay_mas"] is False and last["siguiente"] is None and last["paginas"] == 3
    assert middle["siguiente"] == {"page": 3}


def test_hay_mas_without_total_and_no_paging_keys():
    assert derive_pagination({"offset": 0, "hay_mas": True, "rows": [1, 2]})["siguiente"] == {
        "offset": 2
    }
    assert derive_pagination({"rows": [1, 2]}) is None


# -- resource links -----------------------------------------------------------


def test_resource_links_for_listed_files():
    payload = {
        "archivos": [
            {"titulo": "Boletín", "url": "https://x.gob.ec/a.pdf", "formato": "PDF"},
            {"url": "https://x.gob.ec/datos%202024.zip"},
            {"url": "https://x.gob.ec/a.pdf"},
            {"url": "ftp://nope"},
        ]
    }

    links = resource_links(payload)

    assert [(link.name, str(link.uri), link.mime_type) for link in links] == [
        ("Boletín", "https://x.gob.ec/a.pdf", "application/pdf"),
        ("datos 2024.zip", "https://x.gob.ec/datos%202024.zip", None),
    ]


def test_render_structured_adds_links_and_pagination_after_the_text():
    result = render_structured(
        {"offset": 0, "total": 3, "archivos": [{"url": "https://x.gob.ec/a.csv", "format": "csv"}]},
        "json",
    )

    assert result.content[0].type == "text"
    assert result.content[1].type == "resource_link"
    meta = result.structured_content["metadatos"]
    assert meta["paginacion"]["siguiente"] == {"offset": 1}


# -- stale fallback ------------------------------------------------------------


def test_get_hides_expired_entries_but_serve_stale_returns_them():
    cache = TtlCache(ttl_seconds=0.01, stale_seconds=60)
    cache.set("k", ["last good"])
    time.sleep(0.02)

    assert cache.get("k") is None
    assert cache.serve_stale("k", RuntimeError("down")) == ["last good"]


def test_serve_stale_gives_up_past_the_stale_window():
    cache = TtlCache(ttl_seconds=0.01, stale_seconds=0.01)
    cache.set("k", "old")
    time.sleep(0.05)

    assert cache.serve_stale("k", RuntimeError("down")) is None
    assert cache.serve_stale("missing", RuntimeError("down")) is None


def test_stale_answer_is_flagged_in_the_envelope():
    cache = TtlCache(ttl_seconds=0.01, persist="demo_catalog")
    cache.set("k", "old")
    time.sleep(0.02)
    token = stale_responses.set([])
    try:
        cache.serve_stale("k", TimeoutError("no answer"))
        result = render_structured({"source": "BCE", "rows": []}, "json")
    finally:
        stale_responses.reset(token)

    meta = result.structured_content["metadatos"]
    assert meta["frescura"] == "obsoleta"
    assert meta["respuesta_obsoleta"]["catalogos"] == ["demo_catalog"]
    assert meta["respuesta_obsoleta"]["motivo"].startswith("TimeoutError")


def test_fresh_answers_carry_no_stale_flag():
    token = stale_responses.set([])
    try:
        result = render_structured({"source": "BCE"}, "json")
    finally:
        stale_responses.reset(token)

    assert "respuesta_obsoleta" not in result.structured_content["metadatos"]


def test_stale_entries_survive_a_restart_from_disk(monkeypatch, tmp_path):
    monkeypatch.setenv("ECUADOR_MCP_DISK_CACHE", "1")
    monkeypatch.setattr(cache_module, "data_dir", lambda: tmp_path)
    first = TtlCache(ttl_seconds=0.01, persist="restart_demo")
    first.set("k", {"v": 1})
    time.sleep(0.02)

    second = TtlCache(ttl_seconds=0.01, persist="restart_demo")

    assert second.get("k") is None
    assert second.serve_stale("k", RuntimeError("down")) == {"v": 1}


async def test_a_wrapped_client_answers_from_the_stale_copy(monkeypatch):
    from helpers import inec_client

    fresh_cache = TtlCache(ttl_seconds=0.01, stale_seconds=60)
    fresh_cache.set("topics", [{"titulo": "Empleo", "url": "https://x"}])
    await asyncio.sleep(0.02)
    monkeypatch.setattr(inec_client, "_topics_cache", fresh_cache)

    async def boom():
        raise ConnectionError("ecuadorencifras down")

    monkeypatch.setattr(inec_client, "_fetch_topics_fresh", boom)

    assert await inec_client._fetch_topics() == [{"titulo": "Empleo", "url": "https://x"}]

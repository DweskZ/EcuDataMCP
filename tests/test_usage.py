"""helpers.usage counters, the JSONL log and log_tool's recording."""

import json

import pytest

from helpers import usage
from helpers.logging import log_tool


@pytest.fixture(autouse=True)
def fresh_stats(monkeypatch):
    monkeypatch.setattr(usage, "_stats", {})


async def test_log_tool_records_success_and_failure():
    @log_tool
    async def ok_tool():
        return {"ok": True}

    @log_tool
    async def failing_tool():
        raise RuntimeError("fuente caída")

    await ok_tool()
    with pytest.raises(RuntimeError):
        await failing_tool()

    snap = usage.snapshot()
    assert snap["total_calls"] == 2
    assert snap["tools"]["ok_tool"]["errors"] == 0
    assert snap["tools"]["failing_tool"] == {
        **snap["tools"]["failing_tool"],
        "calls": 1,
        "errors": 1,
    }


def test_no_log_file_unless_enabled(monkeypatch, tmp_path):
    monkeypatch.delenv("ECUADOR_MCP_USAGE_LOG", raising=False)
    monkeypatch.setenv("ECUADOR_MCP_DATA_DIR", str(tmp_path))
    usage.record("search_datasets", ok=True, duration_ms=12.3)
    assert not (tmp_path / "usage.jsonl").exists()


def test_log_file_holds_name_outcome_and_duration_only(monkeypatch, tmp_path):
    monkeypatch.setenv("ECUADOR_MCP_USAGE_LOG", "1")
    monkeypatch.setenv("ECUADOR_MCP_DATA_DIR", str(tmp_path))
    usage.record("get_sri_ruc_info", ok=False, duration_ms=250.4)

    entry = json.loads((tmp_path / "usage.jsonl").read_text(encoding="utf-8"))
    assert set(entry) == {"ts", "tool", "ok", "ms"}
    assert entry["tool"] == "get_sri_ruc_info"
    assert entry["ok"] is False
    assert entry["ms"] == 250


def test_percentile_nearest_rank():
    assert usage.percentile([], 0.5) is None
    assert usage.percentile([10, 20, 30, 40, 50], 0.5) == 30
    assert usage.percentile([10, 20, 30, 40, 50], 0.95) == 50

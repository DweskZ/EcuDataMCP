"""Per-tool usage counters: calls, errors and latency.

docs/MCP_ARCHITECTURE.md (phase 8) keeps saying not to retire or regroup
tools without measuring real calls, and until this module the server
recorded none. Every tool goes through helpers.logging.log_tool, which
calls record() here.

Two views of the same data:
- In memory, for the running process: snapshot() backs the HTTP server's
  /usage endpoint. Lost on restart, and a stdio server lives only as long
  as its client session, so on its own this can't answer "what gets used".
- Optionally on disk: with ECUADOR_MCP_USAGE_LOG=1 each call is appended as
  one JSON line to <data_dir>/usage.jsonl, which survives restarts and
  accumulates across stdio sessions; scripts/usage_report.py summarizes it.

Only the tool name, outcome and duration are recorded -- never arguments,
which can contain RUCs, cédulas or free-text queries. Nothing leaves the
machine.
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from helpers.paths import data_dir

logger = logging.getLogger("ecuador_mcp")

# Enough recent samples for a stable p50/p95 without unbounded memory.
_LATENCY_SAMPLES = 500

_started_at = datetime.now(UTC)
_stats: dict[str, dict[str, Any]] = {}


def usage_log_path() -> Path | None:
    """Return the JSONL path when on-disk logging is enabled, else None."""
    if os.getenv("ECUADOR_MCP_USAGE_LOG", "").strip().lower() not in {"1", "true", "yes"}:
        return None
    return data_dir() / "usage.jsonl"


def record(tool: str, ok: bool, duration_ms: float) -> None:
    stats = _stats.setdefault(
        tool, {"calls": 0, "errors": 0, "latencies": deque(maxlen=_LATENCY_SAMPLES)}
    )
    stats["calls"] += 1
    if not ok:
        stats["errors"] += 1
    stats["latencies"].append(duration_ms)

    path = usage_log_path()
    if path is None:
        return
    line = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "tool": tool,
        "ok": ok,
        "ms": round(duration_ms),
    }
    # A usage log must never be the reason a tool call fails.
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except OSError as e:
        logger.warning("No se pudo escribir el registro de uso %s: %s", path, e)


def percentile(values: list[float], share: float) -> float | None:
    """Nearest-rank percentile, rounded to 0.1 ms; None with no samples."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(share * (len(ordered) - 1)))
    return round(ordered[index], 1)


def snapshot() -> dict[str, Any]:
    tools = {}
    for name, stats in sorted(_stats.items(), key=lambda kv: -kv[1]["calls"]):
        latencies = list(stats["latencies"])
        tools[name] = {
            "calls": stats["calls"],
            "errors": stats["errors"],
            "p50_ms": percentile(latencies, 0.5),
            "p95_ms": percentile(latencies, 0.95),
        }
    return {
        "since": _started_at.isoformat(timespec="seconds"),
        "total_calls": sum(s["calls"] for s in _stats.values()),
        "tools": tools,
    }


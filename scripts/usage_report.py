"""Summarize the usage log written with ECUADOR_MCP_USAGE_LOG=1.

Reads <data_dir>/usage.jsonl (see helpers/usage.py) and prints, per tool,
calls, error rate and p50/p95 latency, then lists the registered tools that
were never called in that period -- the evidence
docs/MCP_ARCHITECTURE.md asks for before retiring or regrouping tools.

Usage:
    uv run python scripts/usage_report.py
    uv run python scripts/usage_report.py --since 2026-10-01 --path other.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.mcpserver import MCPServer

from helpers.paths import data_dir
from helpers.usage import percentile
from tools import register_maintenance_tools, register_tools


def registered_tools() -> set[str]:
    mcp = MCPServer("usage-report")
    register_tools(mcp)
    register_maintenance_tools(mcp)
    return {tool.name for tool in asyncio.run(mcp.list_tools())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", type=Path, default=data_dir() / "usage.jsonl")
    parser.add_argument("--since", default="", help="ISO date; ignore earlier calls")
    args = parser.parse_args()

    if not args.path.exists():
        raise SystemExit(
            f"No usage log at {args.path}. Start the server with ECUADOR_MCP_USAGE_LOG=1."
        )

    calls: dict[str, list[dict]] = defaultdict(list)
    first = last = None
    with open(args.path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry["ts"] < args.since:
                continue
            calls[entry["tool"]].append(entry)
            first = first or entry["ts"]
            last = entry["ts"]

    total = sum(len(v) for v in calls.values())
    print(f"{total} calls from {first} to {last} ({args.path})\n")
    print(f"{'tool':45} {'calls':>6} {'errors':>7} {'p50 ms':>8} {'p95 ms':>8}")
    for tool, entries in sorted(calls.items(), key=lambda kv: -len(kv[1])):
        errors = sum(not e["ok"] for e in entries)
        latencies = [e["ms"] for e in entries]
        print(
            f"{tool:45} {len(entries):>6} {errors / len(entries):>7.0%} "
            f"{percentile(latencies, 0.5):>8} {percentile(latencies, 0.95):>8}"
        )

    never = sorted(registered_tools() - set(calls))
    print(f"\n{len(never)} registered tools never called:")
    for tool in never:
        print(f"  {tool}")


if __name__ == "__main__":
    main()

"""Publish a GitHub release's MCPB bundle to Smithery.

The bundle attached to each release (built by .github/workflows/publish.yml
from manifest.json) can't go to Smithery unchanged, for two reasons found
publishing 0.8.12:

- Smithery's CLI only recognizes the `node`, `python`, `binary` and `bun`
  server types, not MCPB's `uv` type ("Could not determine bundle runtime
  from manifest"). The Smithery copy declares `python`; `mcp_config` still
  launches the server with `uv run`, so behavior is unchanged.
- Without a tool list the release is rejected ("No values to set"), and each
  tool must carry its `inputSchema`, which the MCPB manifest schema forbids.
  So `mcpb pack` can't build this bundle; it is re-zipped here instead, with
  the tool list read from the bundle's own code so it matches the release.

Requires `gh` (to download the release asset), `uv` and `npx`, and a
Smithery CLI login (`npx @smithery/cli auth login`) for the target
namespace.

Usage:
    uv run python scripts/publish_smithery.py              # version from pyproject.toml
    uv run python scripts/publish_smithery.py --version 0.8.12
    uv run python scripts/publish_smithery.py --dry-run    # build the bundle only
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "DweskZ/EcuDataMCP"
DEFAULT_NAME = "dsanchezp998/ecudatamcp"

# Runs inside the extracted bundle, so the tool list comes from the released
# code rather than whatever is checked out here.
# EcuadorMCPServer (0.9.0+) adds the per-parameter descriptions and drops
# schema titles, as the real server does; only the public tools, matching
# the default MCP_PROFILE.
_DUMP_TOOLS = """
import asyncio, json
from helpers.mcp_server import EcuadorMCPServer
from tools import register_tools

mcp = EcuadorMCPServer("dump")
register_tools(mcp)
tools = []
for tool in asyncio.run(mcp.list_tools()):
    card = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
    card.pop("outputSchema", None)
    summary = (tool.description or "").strip().split("\\n\\n")[0]
    card["description"] = summary.replace("\\n", " ")[:300]
    tools.append(card)
print(json.dumps(tools))  # ASCII-only: a Windows child stdout is cp1252
"""


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    # shell=True on Windows so `npx`/`gh` resolve through PATHEXT (.cmd shims).
    return subprocess.run(cmd, check=True, shell=sys.platform == "win32", **kwargs)


def build_bundle(version: str, work: Path) -> Path:
    tag = f"v{version}"
    run(["gh", "release", "download", tag, "-R", REPO, "-p", "*.mcpb", "-D", str(work)])
    source = work / f"ecuador-mcp-{version}.mcpb"
    if not source.exists():
        raise SystemExit(f"release {tag} has no ecuador-mcp-{version}.mcpb asset")

    extracted = work / "bundle"
    with zipfile.ZipFile(source) as archive:
        archive.extractall(extracted)

    # Launched via `uv run`, this script's environment points PYTHONHOME and
    # VIRTUAL_ENV at the checkout's interpreter; the nested `uv run` would
    # inherit them and fail with "SRE module mismatch" on another Python.
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PYTHON", "VIRTUAL_ENV", "UV_"))
    }
    dumped = run(
        ["uv", "run", "-q", "--directory", str(extracted), "python", "-"],
        input=_DUMP_TOOLS,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=clean_env,
    )
    tools = json.loads(dumped.stdout)

    manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != version:
        raise SystemExit(
            f"bundle manifest says {manifest['version']}, expected {version}"
        )
    manifest["manifest_version"] = "0.3"
    manifest["server"]["type"] = "python"
    manifest["tools"] = tools
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")

    # Copy entries from the original archive rather than the extracted tree,
    # which `uv run` has just filled with .venv/ and __pycache__/.
    output = work / f"ecuador-mcp-{version}-smithery.mcpb"
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle,
    ):
        for info in original.infolist():
            name = info.filename.replace("\\", "/")
            content = manifest_bytes if name == "manifest.json" else original.read(info)
            bundle.writestr(name, content)

    print(f"built {output.name}: {len(tools)} tools")
    return output


def main() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default=pyproject["project"]["version"])
    parser.add_argument("--name", default=DEFAULT_NAME, help="Smithery namespace/id")
    parser.add_argument(
        "--out",
        type=Path,
        help="keep the built bundle in this directory (default: discard)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="build the bundle, don't publish"
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        bundle = build_bundle(args.version, Path(tmp))
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            kept = args.out / bundle.name
            kept.write_bytes(bundle.read_bytes())
            print(f"saved {kept}")
        if not args.dry_run:
            run(
                [
                    "npx",
                    "-y",
                    "@smithery/cli@latest",
                    "mcp",
                    "publish",
                    str(bundle),
                    "-n",
                    args.name,
                ]
            )


if __name__ == "__main__":
    main()

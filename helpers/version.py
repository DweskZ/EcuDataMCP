"""Single source of truth for the server's version string.

Before this existed, main.py's VERSION and list_capabilities' hardcoded
"version" field were two independent literals that had to be bumped by
hand on every release -- they drifted (list_capabilities sat at "0.8.2"
for three releases while the real version moved to 0.8.5). Never hardcode
the version anywhere else; import get_version() instead.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from importlib import metadata
from pathlib import Path

_PACKAGE_NAME = "ecuador-mcp"


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return the running server's version.

    Prefers the installed distribution's metadata (correct as soon as
    `uv sync`/`pip install -e .` has run). Falls back to reading
    pyproject.toml directly for the rare case of executing straight from a
    checkout with no install step.
    """
    try:
        return metadata.version(_PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            return data["project"]["version"]
        except Exception:
            return "unknown"

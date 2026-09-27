"""Where the server keeps files it writes at runtime.

The Supercías financials DB and the BCE snapshot/review stores used to sit
at `<package parent>/data`, which is only right for a source checkout (git
clone, Docker, an MCPB bundle). Installed from PyPI that parent is
site-packages -- or a throwaway uvx cache -- so they now go to a per-user
data directory instead.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_NAME = "ecuador-mcp"
_ROOT = Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    """Return the directory for runtime-written data (not created here).

    `ECUADOR_MCP_DATA_DIR` wins; otherwise a source checkout (pyproject.toml
    next to the package) keeps using its own `data/`, and an installed
    package uses the platform's per-user data directory.
    """
    override = os.getenv("ECUADOR_MCP_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if (_ROOT / "pyproject.toml").is_file():
        return _ROOT / "data"
    if sys.platform == "win32":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / _APP_NAME

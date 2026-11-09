"""Build/refresh helpers/data/censo_tabulados_index.json by hand.

The build itself lives in helpers/censo_index_build.py so installs without
scripts/ (PyPI, MCPB bundles) can run it too; this wrapper is the repo-checkout
shortcut.

Usage:
    uv run python scripts/build_censo_index.py [--out PATH] [--max-mb 25]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpers.censo_index_build import main

if __name__ == "__main__":
    sys.exit(main())

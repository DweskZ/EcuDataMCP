"""Build/refresh the Supercías financials DB by hand.

The build itself lives in helpers/supercias_financials_build.py so installs
without scripts/ (PyPI, MCPB bundles) can run it too; this wrapper keeps the
old command working.

Usage:
    uv run python scripts/build_supercias_financials_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpers.supercias_financials_build import main

if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# Build and serve the landing page on http://127.0.0.1:8765
set -euo pipefail
cd "$(dirname "$0")"
uv sync --quiet
uv run python build.py
cd _site
echo "EcuDataMCP site → http://127.0.0.1:8765"
exec python3 -m http.server 8765

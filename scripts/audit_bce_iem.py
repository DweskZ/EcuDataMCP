"""Build and persist a complete historical IEM table catalog.

This is intentionally an operator/scheduler job, not an MCP request: scanning
every monthly bulletin since 1996 can involve hundreds of bulletin pages.  The
full catalog is written under ``IEM_CATALOG_DIR`` (or
``data/iem_catalog_snapshots``), while the console output stays bounded.

Usage:
    uv run python scripts/audit_bce_iem.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime

from helpers import bce_iem_client


async def _run() -> int:
    result = await bce_iem_client.search_tables(
        historico=True,
        desde_anio=1996,
        hasta_anio=datetime.now(UTC).year,
        limit=1,
        guardar_catalogo=True,
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key != "tablas"
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0 if result.get("boletines_sin_tablas", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))

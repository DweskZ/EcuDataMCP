"""Persist one BCEData catalog audit for scheduled/operator use.

The output directory defaults to ``data/bce_catalog_snapshots`` and can be
changed with ``BCE_CATALOG_SNAPSHOT_DIR``.  A partial audit is saved as an
attempt but exits non-zero and leaves the last complete snapshot untouched.

Usage:
    uv run python scripts/audit_bce_catalog.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from helpers import bce_client


async def _run(auditar_grid: bool) -> int:
    result = await bce_client.audit_catalog(
        incluir_grupos=True,
        guardar_snapshot=True,
        comparar_anterior=True,
        auditar_grid=auditar_grid,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 1 if result.get("grupos_con_error") else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auditar-grid",
        action="store_true",
        help="Probar una combinación frecuencia/unidad reciente por grupo",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.auditar_grid)))

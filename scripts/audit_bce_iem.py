"""Build and persist a complete historical IEM table catalog.

This is intentionally an operator/scheduler job, not an MCP request: scanning
every monthly bulletin since 1996 can involve hundreds of bulletin pages.  The
full catalog is written under ``IEM_CATALOG_DIR`` (or
``data/iem_catalog_snapshots``), while the console output stays bounded.

Usage:
    uv run python scripts/audit_bce_iem.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime

from helpers import bce_iem_client


async def _run(
    hash_xlsx: bool, max_hash_files: int, desde_anio: int, hasta_anio: int
) -> int:
    result = await bce_iem_client.search_tables(
        historico=True,
        desde_anio=desde_anio,
        hasta_anio=hasta_anio or datetime.now(UTC).year,
        limit=10_000,
        guardar_catalogo=True,
        hash_archivos=hash_xlsx,
        max_hash_archivos=max_hash_files,
    )
    years = [
        version.get("boletin_anio", 0)
        for table in result.get("tablas", [])
        for version in table.get("versiones", [table])
        if version.get("boletin_anio")
    ]
    first_year = min(years, default=0)
    coverage = {
        "desde_anio_solicitado": desde_anio,
        "desde_anio_encontrado": first_year or None,
        "hasta_anio_encontrado": result["boletin"].get("anio"),
        "completa_desde_anio_solicitado": bool(first_year and first_year <= desde_anio),
    }
    result["cobertura_historica"] = coverage
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
    return 0 if (
        result.get("boletines_sin_tablas", 0) == 0
        and coverage["completa_desde_anio_solicitado"]
    ) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hash-xlsx",
        action="store_true",
        help="Descargar y calcular SHA-256 de los XLSX descubiertos",
    )
    parser.add_argument(
        "--max-hash-files",
        type=int,
        default=5000,
        help="Máximo de XLSX a descargar para el manifiesto (1-5000)",
    )
    parser.add_argument(
        "--desde-anio",
        type=int,
        default=1996,
        help="Año inicial requerido para declarar cobertura histórica completa",
    )
    parser.add_argument(
        "--hasta-anio",
        type=int,
        default=0,
        help="Año final para un barrido acotado; por defecto, el año actual",
    )
    args = parser.parse_args()
    sys.exit(
        asyncio.run(
            _run(args.hash_xlsx, args.max_hash_files, args.desde_anio, args.hasta_anio)
        )
    )

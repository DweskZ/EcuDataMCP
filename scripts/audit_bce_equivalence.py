"""Generate a persistent review queue for BCEData ↔ IEM candidates.

This does not declare any candidate a methodological equivalence.  It leaves
the labels, alternative matches and required review fields in one durable JSON
file for an analyst or a scheduled deployment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from helpers import bce_client, bce_equivalence, bce_equivalence_store, bce_iem_client


async def _run(historico: bool) -> int:
    bcedata = await bce_client._fetch_catalog_snapshot()
    iem = await bce_iem_client.search_tables(historico=historico, limit=10_000)
    result = bce_equivalence.build_equivalence_map(bcedata, iem)
    result["bce_consultado_en"] = bcedata.get("consultado_en")
    result["iem_consultado_en"] = iem.get("catalogado_en")
    result["revision_guardada"] = bce_equivalence_store.persist_review_map(result)
    relations = {}
    for item in result["equivalencias_candidatas"]:
        relation = item["relacion"]
        relations[relation] = relations.get(relation, 0) + 1
    print(
        json.dumps(
            {
                "equivalencias_candidatas": len(result["equivalencias_candidatas"]),
                "iem_solo_por_etiquetas": len(result["iem_solo_por_etiquetas"]),
                "bcedata_solo_por_etiquetas": len(result["bcedata_solo_por_etiquetas"]),
                "candidatos_por_relacion": relations,
                "revision_guardada": result["revision_guardada"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--historico",
        action="store_true",
        help="Comparar las versiones IEM disponibles en el archivo histórico",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.historico)))

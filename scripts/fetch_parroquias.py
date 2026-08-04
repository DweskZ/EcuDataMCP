"""Refresh helpers/data/parroquias.json from ArcGIS Parroquias_del_Ecuador."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "helpers" / "data" / "parroquias.json"
BASE = (
    "https://services7.arcgis.com/iFGeGXTAJXnjq0YN/ArcGIS/rest/services/"
    "Parroquias_del_Ecuador/FeatureServer/0/query"
)
FIELDS = "DPA_PARROQ,DPA_DESPAR,DPA_CANTON,DPA_DESCAN,DPA_PROVIN,DPA_DESPRO"


def main() -> None:
    rows: list[dict] = []
    offset = 0
    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        while True:
            resp = client.get(
                BASE,
                params={
                    "where": "1=1",
                    "outFields": FIELDS,
                    "returnGeometry": "false",
                    "f": "json",
                    "resultOffset": offset,
                    "resultRecordCount": 1000,
                    "orderByFields": "DPA_PARROQ ASC",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            feats = data.get("features") or []
            if not feats:
                break
            for feat in feats:
                a = feat.get("attributes") or {}
                rows.append(
                    {
                        "codigo": (a.get("DPA_PARROQ") or "").strip(),
                        "nombre": (a.get("DPA_DESPAR") or "").strip().title(),
                        "canton_codigo": (a.get("DPA_CANTON") or "").strip(),
                        "canton": (a.get("DPA_DESCAN") or "").strip().title(),
                        "provincia_codigo": (a.get("DPA_PROVIN") or "").strip(),
                        "provincia": (a.get("DPA_DESPRO") or "").strip().title(),
                    }
                )
            print(f"batch={len(feats)} total={len(rows)}")
            if not data.get("exceededTransferLimit"):
                break
            offset += len(feats)

    uniq = {r["codigo"]: r for r in rows if r["codigo"]}
    ordered = sorted(uniq.values(), key=lambda x: x["codigo"])
    OUT.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} count={len(ordered)}")


if __name__ == "__main__":
    main()

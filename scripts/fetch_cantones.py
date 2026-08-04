"""One-off helper to refresh helpers/data/cantones.json from ArcGIS."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "helpers" / "data" / "cantones.json"
BASE = (
    "https://services7.arcgis.com/iFGeGXTAJXnjq0YN/arcgis/rest/services/"
    "Cantones_del_Ecuador/FeatureServer/0/query"
)
FIELDS = "DPA_CANTON,DPA_DESCAN,DPA_PROVIN,DPA_DESPRO,REN_REGION,AREA_KM2,TOTPOP"


def main() -> None:
    cantones: list[dict] = []
    offset = 0
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        while True:
            resp = client.get(
                BASE,
                params={
                    "where": "1=1",
                    "outFields": FIELDS,
                    "returnGeometry": "false",
                    "f": "json",
                    "resultOffset": offset,
                    "resultRecordCount": 200,
                    "orderByFields": "DPA_CANTON ASC",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            feats = data.get("features") or []
            if not feats:
                break
            for feat in feats:
                attrs = feat.get("attributes") or {}
                cantones.append(
                    {
                        "codigo": (attrs.get("DPA_CANTON") or "").strip(),
                        "nombre": (attrs.get("DPA_DESCAN") or "").strip().title(),
                        "provincia_codigo": (attrs.get("DPA_PROVIN") or "").strip(),
                        "provincia": (attrs.get("DPA_DESPRO") or "").strip().title(),
                        "region": (attrs.get("REN_REGION") or "").strip().title(),
                        "area_km2": attrs.get("AREA_KM2"),
                        "poblacion": attrs.get("TOTPOP"),
                    }
                )
            print(f"batch={len(feats)} total={len(cantones)}")
            if not data.get("exceededTransferLimit"):
                break
            offset += len(feats)

    uniq = {c["codigo"]: c for c in cantones if c["codigo"]}
    ordered = sorted(uniq.values(), key=lambda x: x["codigo"])
    OUT.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} count={len(ordered)}")


if __name__ == "__main__":
    main()

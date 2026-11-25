"""One-off helper to refresh helpers/data/cantones_centroides.json from ArcGIS.

Same Cantones_del_Ecuador layer as fetch_cantones.py, asked for each polygon's
centroid in WGS84. The centroid is the geometric centre of the canton, not
the seat of the city, and for a canton with islands or a coastline it can
fall in the sea.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
# The layer still lists La Concordia under Esmeraldas (0808); the INEC classifier
# in cantones.json has it in Santo Domingo de los Tsáchilas (2302).
RENAMED_CODES = {"0808": "2302"}
OUT = ROOT / "helpers" / "data" / "cantones_centroides.json"
BASE = (
    "https://services7.arcgis.com/iFGeGXTAJXnjq0YN/arcgis/rest/services/"
    "Cantones_del_Ecuador/FeatureServer/0/query"
)


def main() -> None:
    centroides: dict[str, dict[str, float]] = {}
    offset = 0
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        while True:
            resp = client.get(
                BASE,
                params={
                    "where": "1=1",
                    "outFields": "DPA_CANTON",
                    "returnGeometry": "false",
                    "returnCentroid": "true",
                    "outSR": 4326,
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
                codigo = ((feat.get("attributes") or {}).get("DPA_CANTON") or "").strip()
                codigo = RENAMED_CODES.get(codigo, codigo)
                centroid = feat.get("centroid") or {}
                if codigo and centroid.get("x") is not None:
                    centroides[codigo] = {
                        "latitud": round(centroid["y"], 4),
                        "longitud": round(centroid["x"], 4),
                    }
            print(f"batch={len(feats)} total={len(centroides)}")
            if not data.get("exceededTransferLimit"):
                break
            offset += len(feats)

    ordered = dict(sorted(centroides.items()))
    OUT.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} count={len(ordered)}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json

from helpers import bce_catalog_store


def _snapshot(series: list[str], errors: list[dict] | None = None) -> dict:
    return {
        "source": "BCEData",
        "url_fuente": "https://example.test/tree",
        "consultado_en": "2026-08-31T00:00:00+00:00",
        "total_nodos": 2,
        "total_grupos": 1,
        "grupos": [
            {
                "id_grupo": 10,
                "descripcion": "Grupo",
                "seccion": "Sección",
                "subseccion": "Subsección",
                "nombre": "Grupo",
                "series": series,
                "total_series": len(series),
                "frecuencias": ["Mensual"],
                "unidades": {"Mensual": ["Número"]},
                "rango": {"minYm": "2020-01", "maxYm": "2026-06"},
                "rango_por_frecuencia": {
                    "Mensual": {"minYm": "2020-01", "maxYm": "2026-06"}
                },
                "bundle_ok": True,
            }
        ],
        "errores": errors or [],
    }


def test_compare_snapshots_reports_series_change():
    previous = _snapshot(["Serie A"])
    current = _snapshot(["Serie A", "Serie B"])

    result = bce_catalog_store.compare_snapshots(previous, current)

    assert result["disponible"] is True
    assert result["total_cambios"] == 1
    assert result["grupos_modificados"][0]["id_grupo"] == 10


def test_persist_snapshot_keeps_partial_attempt_from_latest_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("BCE_CATALOG_SNAPSHOT_DIR", str(tmp_path))
    valid = _snapshot(["Serie A"])
    partial = _snapshot(["Serie A"], errors=[{"id_grupo": 10}])

    valid_info = bce_catalog_store.persist_snapshot(valid)
    partial_info = bce_catalog_store.persist_snapshot(partial)

    assert valid_info["completo"] is True
    assert partial_info["completo"] is False
    with (tmp_path / "latest-valid.json").open(encoding="utf-8") as handle:
        saved = json.load(handle)
    assert saved["errores"] == []
    assert (tmp_path / "latest-attempt.json").exists()
    assert len(list(tmp_path.glob("snapshot-*.json"))) == 2
    assert (
        bce_catalog_store.snapshot_fingerprint(saved)
        == bce_catalog_store.snapshot_fingerprint(valid)
    )

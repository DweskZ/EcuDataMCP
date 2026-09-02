import json

from helpers import bce_equivalence_store


def test_persist_review_map_keeps_latest_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("BCE_EQUIVALENCE_REVIEW_DIR", str(tmp_path))

    saved = bce_equivalence_store.persist_review_map({"equivalencias_candidatas": []})

    assert saved["archivo"].endswith(".json")
    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest["equivalencias_candidatas"] == []
    assert latest["revision_generada_en"]

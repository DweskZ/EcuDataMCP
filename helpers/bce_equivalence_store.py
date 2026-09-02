"""Durable review manifests for tentative BCEData ↔ IEM equivalences."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DIR = _ROOT / "data" / "bce_equivalence_reviews"


def review_dir() -> Path:
    configured = os.getenv("BCE_EQUIVALENCE_REVIEW_DIR", "").strip()
    return Path(configured) if configured else _DEFAULT_DIR


def persist_review_map(review: dict[str, Any]) -> dict[str, str]:
    """Atomically save a candidate map and promote it as the latest review."""
    directory = review_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = re.sub(
        r"[^0-9A-Za-z_.-]+", "-", datetime.now(UTC).isoformat()
    ).strip("-")
    payload = {**review, "revision_generada_en": datetime.now(UTC).isoformat()}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    path = directory / f"equivalencias-{stamp}.json"
    temporary = directory / f".{path.name}.tmp"
    temporary.write_bytes(raw)
    temporary.replace(path)
    latest = directory / "latest.json"
    temporary_latest = directory / ".latest.json.tmp"
    temporary_latest.write_bytes(raw)
    temporary_latest.replace(latest)
    return {"directorio": str(directory), "archivo": str(path)}

"""Offline geographic reference data (INEC DPA province codes)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from unicodedata import category, normalize

_DATA_PATH = Path(__file__).resolve().parent / "data" / "provincias.json"


def _strip(text: str) -> str:
    nfkd = normalize("NFKD", text or "")
    return "".join(c for c in nfkd if category(c) != "Mn").lower()


@lru_cache(maxsize=1)
def list_provincias() -> list[dict[str, Any]]:
    with _DATA_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return list(data)


def find_provincias(query: str = "", region: str = "") -> list[dict[str, Any]]:
    items = list_provincias()
    q = _strip(query)
    r = _strip(region)
    out: list[dict[str, Any]] = []
    for p in items:
        if r and r not in _strip(p.get("region", "")):
            continue
        if not q:
            out.append(p)
            continue
        fields = (
            _strip(p.get("codigo", "")),
            _strip(p.get("nombre", "")),
            _strip(p.get("capital", "")),
        )
        if any(q == f or q in f for f in fields):
            out.append(p)
    return out

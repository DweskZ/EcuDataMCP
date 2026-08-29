"""Curated pointer to BIINEC's handful of genuinely exclusive registries.

BIINEC (aplicaciones3.ecuadorencifras.gob.ec/BIINEC-war) mostly duplicates
ANDA and ecuadorencifras.gob.ec/estadisticas/ behind a much costlier JSF
session flow (multi-step ViewState postbacks, no static download URLs) — see
RESEARCH.md § Ecuador en Cifras. Automating that flow isn't worth it for the
handful of items it doesn't duplicate: this is a small, manually-verified
list of those items instead, with directions to find them by hand. Anything
not in this list should be searched on the site directly — this is
deliberately not a live scraper or a general BIINEC client.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from helpers.text_utils import strip_accents as _strip_accents

BIINEC_URL = "https://aplicaciones3.ecuadorencifras.gob.ec/BIINEC-war/index.xhtml"

_DATA_PATH = Path(__file__).resolve().parent / "data" / "biinec_extras.json"


@lru_cache(maxsize=1)
def list_extras() -> list[dict[str, Any]]:
    with _DATA_PATH.open(encoding="utf-8") as fh:
        return list(json.load(fh))


def search_extras(query: str = "") -> list[dict[str, Any]]:
    """Accent-insensitive keyword match against the curated list's name/description."""
    items = list_extras()
    q = _strip_accents(query)
    if not q:
        return items
    return [
        item
        for item in items
        if q in _strip_accents(item["nombre"]) or q in _strip_accents(item["descripcion"])
    ]

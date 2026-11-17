"""Committed index of the Census 2022 tabulados (see censo_index_build.py).

Read-only at runtime: `data/censo_tabulados_index.json` holds, per tabulado
workbook, its URL, SHA-256, extraction date and one record per sheet (table
title, geographic levels, column headers). `search_archivos(fuente="censo")`
matches queries against it, and falls back to it for the file list when the
census site cannot be reached.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents

logger = logging.getLogger(MAIN_LOGGER_NAME)

INDEX_PATH = Path(__file__).resolve().parent / "data" / "censo_tabulados_index.json"


@lru_cache(maxsize=1)
def load_index() -> dict[str, Any]:
    """The committed index, or an empty one if it is missing or unreadable."""
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("archivos"), list):
            return data
    except (OSError, ValueError) as exc:
        logger.warning("Census tabulados index unreadable, ignoring it: %s", exc)
    return {"archivos": [], "omitidos": []}


def _base_label(label: str) -> str:
    """"Etnia – Excel" / "Etnia – CSV" -> "Etnia" (both formats share one workbook)."""
    return label.rsplit(" – ", 1)[0].strip()


def sheets_for(url: str, label: str) -> list[dict[str, Any]]:
    """Indexed tables of the workbook behind a resource.

    The XLSX is found by URL; its CSV twin (same "Name – CSV" label stem on the
    census page) shares the same tables.
    """
    index = load_index()
    for entry in index["archivos"]:
        if entry["url"] == url:
            return entry["hojas"]
    stem = strip_accents(_base_label(label))
    for entry in index["archivos"]:
        if strip_accents(_base_label(entry["label"])) == stem:
            return entry["hojas"]
    return []


def indexed_resources() -> list[dict[str, Any]]:
    """The tabulado workbooks of the index as census-resource entries (offline list)."""
    out = []
    for entry in load_index()["archivos"]:
        resource: dict[str, Any] = {
            "url": entry["url"],
            "label": entry["label"],
            "format": entry.get("formato", "XLSX"),
            "tipo": "tabulado",
            "anio": "2022",
        }
        if entry.get("tema"):
            resource["tema"] = entry["tema"]
        out.append(resource)
    return out


def sheet_text(sheet: dict[str, Any]) -> str:
    """Accent-free searchable text of one indexed table."""
    parts = [
        sheet.get("hoja"),
        sheet.get("titulo"),
        " ".join(sheet.get("niveles", [])),
        " ".join(sheet.get("columnas", [])),
    ]
    return strip_accents(" ".join(str(p) for p in parts if p))

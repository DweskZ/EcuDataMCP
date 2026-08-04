"""Offline geographic reference data (INEC DPA provinces, cantons, parroquias)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from unicodedata import category, normalize

_DATA_DIR = Path(__file__).resolve().parent / "data"
_PROVINCIAS_PATH = _DATA_DIR / "provincias.json"
_CANTONES_PATH = _DATA_DIR / "cantones.json"
_PARROQUIAS_PATH = _DATA_DIR / "parroquias.json"


def _strip(text: str) -> str:
    nfkd = normalize("NFKD", text or "")
    return "".join(c for c in nfkd if category(c) != "Mn").lower()


@lru_cache(maxsize=1)
def list_provincias() -> list[dict[str, Any]]:
    with _PROVINCIAS_PATH.open(encoding="utf-8") as fh:
        return list(json.load(fh))


@lru_cache(maxsize=1)
def list_cantones() -> list[dict[str, Any]]:
    with _CANTONES_PATH.open(encoding="utf-8") as fh:
        return list(json.load(fh))


@lru_cache(maxsize=1)
def list_parroquias() -> list[dict[str, Any]]:
    with _PARROQUIAS_PATH.open(encoding="utf-8") as fh:
        return list(json.load(fh))


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


def find_cantones(
    query: str = "",
    provincia: str = "",
    region: str = "",
) -> list[dict[str, Any]]:
    items = list_cantones()
    q = _strip(query)
    p = _strip(provincia)
    r = _strip(region)
    out: list[dict[str, Any]] = []
    for c in items:
        if r and r not in _strip(c.get("region", "")):
            continue
        if p:
            prov_blob = _strip(f"{c.get('provincia', '')} {c.get('provincia_codigo', '')}")
            if p not in prov_blob:
                continue
        if not q:
            out.append(c)
            continue
        fields = (
            _strip(c.get("codigo", "")),
            _strip(c.get("nombre", "")),
            _strip(c.get("provincia", "")),
        )
        if any(q == f or q in f for f in fields):
            out.append(c)
    return out


def find_parroquias(
    query: str = "",
    canton: str = "",
    provincia: str = "",
) -> list[dict[str, Any]]:
    items = list_parroquias()
    q = _strip(query)
    c = _strip(canton)
    p = _strip(provincia)
    out: list[dict[str, Any]] = []
    for row in items:
        if p:
            prov_blob = _strip(
                f"{row.get('provincia', '')} {row.get('provincia_codigo', '')}"
            )
            if p not in prov_blob:
                continue
        if c:
            can_blob = _strip(f"{row.get('canton', '')} {row.get('canton_codigo', '')}")
            if c not in can_blob:
                continue
        if not q:
            out.append(row)
            continue
        fields = (
            _strip(row.get("codigo", "")),
            _strip(row.get("nombre", "")),
            _strip(row.get("canton", "")),
            _strip(row.get("provincia", "")),
        )
        if any(q == f or q in f for f in fields):
            out.append(row)
    return out

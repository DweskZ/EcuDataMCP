"""Offline geographic reference data (INEC DPA provinces, cantons, parroquias)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from helpers.text_utils import strip_accents as _strip

_DATA_DIR = Path(__file__).resolve().parent / "data"
_PROVINCIAS_PATH = _DATA_DIR / "provincias.json"
_CANTONES_PATH = _DATA_DIR / "cantones.json"
_PARROQUIAS_PATH = _DATA_DIR / "parroquias.json"
_PARROQUIAS_URBANAS_PATH = _DATA_DIR / "parroquias_urbanas.json"

# Year of the INEC classifier (CODIFICACIÓN_2026.xlsx, sheet PARROQUIAS) that
# parroquias_urbanas.json was built from.
CLASIFICADOR_ANIO = 2026


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


@lru_cache(maxsize=1)
def list_parroquias_urbanas() -> list[dict[str, Any]]:
    """Urban parishes (DPA_PARURB), each mapped to its head parish (DPA_PARROQ).

    Death, police and ECU 911 records name these (e.g. Tarqui 090112), while
    the head-parish list only has the city's head parish (Guayaquil 090150).
    """
    with _PARROQUIAS_URBANAS_PATH.open(encoding="utf-8") as fh:
        rows = json.load(fh)
    return [
        {
            "codigo_parroquia_urbana": r["codigo"],
            "nombre": r["nombre"],
            "codigo": r["parroquia_codigo"],
            "parroquia": r["parroquia"],
            "canton_codigo": r["canton_codigo"],
            "canton": r["canton"],
            "provincia_codigo": r["provincia_codigo"],
            "provincia": r["provincia"],
            "clasificador_anio": CLASIFICADOR_ANIO,
        }
        for r in rows
    ]


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


def find_parroquias_urbanas(
    query: str = "",
    canton: str = "",
    provincia: str = "",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    q = _strip(query)
    c = _strip(canton)
    p = _strip(provincia)
    for row in list_parroquias_urbanas():
        if p and p not in _strip(f"{row['provincia']} {row['provincia_codigo']}"):
            continue
        if c and c not in _strip(f"{row['canton']} {row['canton_codigo']}"):
            continue
        if q:
            fields = (
                _strip(row["codigo_parroquia_urbana"]),
                _strip(row["nombre"]),
                _strip(row["parroquia"]),
                _strip(row["canton"]),
                _strip(row["provincia"]),
            )
            if not any(q == f or q in f for f in fields):
                continue
        out.append(row)
    return out

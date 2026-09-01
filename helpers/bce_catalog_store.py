"""Durable storage and comparison for BCEData catalog audits.

The MCP process normally keeps BCEData metadata in memory.  This small store
adds an optional on-disk audit trail for operators who want to detect source
drift between runs.  Writes are atomic, and a failed/partial audit never
replaces the last complete snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DIR = _ROOT / "data" / "bce_catalog_snapshots"
_LATEST_VALID = "latest-valid.json"
_LATEST_ATTEMPT = "latest-attempt.json"
_LATEST_GRID_AUDIT = "latest-grid-audit.json"
_TIMESTAMP_RE = re.compile(r"[^0-9A-Za-z_.-]+")


def snapshot_dir() -> Path:
    """Return the configured directory without creating it."""
    configured = os.getenv("BCE_CATALOG_SNAPSHOT_DIR", "").strip()
    return Path(configured) if configured else _DEFAULT_DIR


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    """Hash the catalog content while ignoring the time of the audit."""
    comparable = {
        key: value
        for key, value in snapshot.items()
        if key not in {"consultado_en", "snapshot_id", "huella", "persistido_en"}
    }
    return hashlib.sha256(_json_bytes(comparable)).hexdigest()


def _group_comparable(group: dict[str, Any]) -> dict[str, Any]:
    return {
        key: group.get(key)
        for key in (
            "id_grupo",
            "descripcion",
            "seccion",
            "subseccion",
            "nombre",
            "series",
            "frecuencias",
            "unidades",
            "rango",
            "rango_por_frecuencia",
            "bundle_ok",
        )
    }


def compare_snapshots(
    previous: dict[str, Any] | None, current: dict[str, Any]
) -> dict[str, Any]:
    """Describe catalog groups and series that changed since ``previous``."""
    if previous is None:
        return {
            "disponible": False,
            "mensaje": "No existe un snapshot BCEData completo anterior.",
            "grupos_nuevos": [],
            "grupos_retirados": [],
            "grupos_modificados": [],
        }

    old_revision = previous.get("revision_fuente") or {}
    new_revision = current.get("revision_fuente") or {}
    revision_comparable = (
        old_revision.get("disponible") is True
        and new_revision.get("disponible") is True
    )
    revision_changed = (
        revision_comparable
        and old_revision.get("valor") != new_revision.get("valor")
    )

    old = {
        str(item["id_grupo"]): item
        for item in previous.get("grupos", [])
        if isinstance(item, dict) and item.get("id_grupo") is not None
    }
    new = {
        str(item["id_grupo"]): item
        for item in current.get("grupos", [])
        if isinstance(item, dict) and item.get("id_grupo") is not None
    }
    added = sorted(set(new) - set(old), key=int)
    removed = sorted(set(old) - set(new), key=int)
    changed: list[dict[str, Any]] = []
    for group_id in sorted(set(old) & set(new), key=int):
        before = _group_comparable(old[group_id])
        after = _group_comparable(new[group_id])
        if before == after:
            continue
        changed_fields = [
            key for key in before if before[key] != after[key]
        ]
        series_before = set(before.get("series") or [])
        series_after = set(after.get("series") or [])
        changed.append(
            {
                "id_grupo": new[group_id]["id_grupo"],
                "campos_modificados": changed_fields,
                "series_nuevas": sorted(series_after - series_before),
                "series_retiradas": sorted(series_before - series_after),
                "antes": before,
                "despues": after,
            }
        )
    return {
        "disponible": True,
        "snapshot_anterior": previous.get("consultado_en"),
        "huella_anterior": snapshot_fingerprint(previous),
        "huella_actual": snapshot_fingerprint(current),
        "revision": {
            "comparable": revision_comparable,
            "cambio_detectado": revision_changed,
            "anterior": old_revision,
            "actual": new_revision,
        },
        "grupos_nuevos": [new[group_id] for group_id in added],
        "grupos_retirados": [old[group_id] for group_id in removed],
        "grupos_modificados": changed,
        "total_cambios": len(added) + len(removed) + len(changed),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_latest_valid() -> dict[str, Any] | None:
    return _read_json(snapshot_dir() / _LATEST_VALID)


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(_json_bytes(value))
    temporary.replace(path)


def persist_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Persist an attempt and promote it only when every group succeeded."""
    directory = snapshot_dir()
    now = datetime.now(UTC)
    stamp = (
        _TIMESTAMP_RE.sub("-", now.isoformat()).strip("-")
        + "-"
        + uuid4().hex[:12]
    )
    enriched = {
        **snapshot,
        "snapshot_id": stamp,
        "huella": snapshot_fingerprint(snapshot),
        "persistido_en": now.isoformat(),
    }
    _atomic_write(directory / f"snapshot-{stamp}.json", enriched)
    _atomic_write(directory / _LATEST_ATTEMPT, enriched)

    errors = enriched.get("errores") or []
    complete = not errors and enriched.get("total_grupos") == len(
        enriched.get("grupos") or []
    )
    if complete:
        _atomic_write(directory / _LATEST_VALID, enriched)
    return {
        "directorio": str(directory),
        "archivo": str(directory / f"snapshot-{stamp}.json"),
        "completo": complete,
        "huella": enriched["huella"],
    }


def persist_grid_audit(audit: dict[str, Any]) -> dict[str, Any]:
    """Persist a bounded value-probe report separately from catalog metadata."""
    directory = snapshot_dir()
    now = datetime.now(UTC)
    stamp = (
        _TIMESTAMP_RE.sub("-", now.isoformat()).strip("-")
        + "-"
        + uuid4().hex[:12]
    )
    enriched = {**audit, "persistido_en": now.isoformat(), "auditoria_id": stamp}
    path = directory / f"grid-audit-{stamp}.json"
    _atomic_write(path, enriched)
    _atomic_write(directory / _LATEST_GRID_AUDIT, enriched)
    return {"directorio": str(directory), "archivo": str(path)}

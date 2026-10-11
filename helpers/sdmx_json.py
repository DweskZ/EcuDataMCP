"""Flatten an SDMX-JSON data message (IMF SDMX 2.1 JSON v1 and the ILO's
sdmx-json 2.0) into one list of series.

Both formats key each series by dimension-value positions ("0:3:1") and each
observation by a time-value position, so the structure block is needed to
turn them back into codes, names and period labels. The structure of the
response lists only the values that actually appear in it, which makes the
dimension order of a dataflow readable straight from a data call.
"""

from __future__ import annotations

from typing import Any


def _number(raw: Any) -> float | int | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return int(value) if value.is_integer() and abs(value) < 1e15 else value


def parse(payload: dict[str, Any], max_series: int = 100) -> dict[str, Any]:
    """Return {titulo, dimensiones, total_series, series} from an SDMX-JSON
    message."""
    if "structure" in payload:  # IMF (SDMX-JSON 1.0)
        structure = payload["structure"]
        dataset = (payload.get("dataSets") or [{}])[0]
        title = structure.get("name")
    else:  # ILO (SDMX-JSON 2.0)
        data = payload.get("data") or {}
        structure = (data.get("structures") or [{}])[0]
        dataset = (data.get("dataSets") or [{}])[0]
        title = None
    dims = structure.get("dimensions", {})
    series_dims = sorted(dims.get("series", []), key=lambda d: d.get("keyPosition", 0))
    obs_dims = dims.get("observation") or [{"values": []}]
    periods = [v.get("id") or v.get("name") for v in obs_dims[0].get("values", [])]

    series = []
    for key, body in (dataset.get("series") or {}).items():
        positions = [int(i) for i in key.split(":")]
        coded = []
        for dim, pos in zip(series_dims, positions, strict=False):
            value = dim["values"][pos]
            coded.append((dim["id"], value.get("id"), value.get("name") or value.get("id")))
        observations = [
            {"periodo": periods[int(i)], "valor": _number(obs[0])}
            for i, obs in sorted(body.get("observations", {}).items(), key=lambda kv: int(kv[0]))
            if obs and int(i) < len(periods)
        ]
        series.append(
            {
                "clave": ".".join(str(code) for _, code, _ in coded),
                "dimensiones": {
                    dim_id: {"codigo": code, "nombre": name} for dim_id, code, name in coded
                },
                "observaciones": observations,
            }
        )
    return {
        "titulo": title,
        "dimensiones": [
            {
                "posicion": i + 1,
                "id": d["id"],
                "nombre": d.get("name"),
                "valores_en_respuesta": len(d["values"]),
            }
            for i, d in enumerate(series_dims)
        ],
        "total_series": len(series),
        "series": series[:max_series],
    }

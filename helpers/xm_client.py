"""Client for XM (Colombia's market operator) public API `servapibi.xm.com.co`,
no key. Used for the hourly energy flows on the Colombia-Ecuador
interconnection, the only source with 2003-present depth (docs/RESEARCH.md
§ Trigésimo quinta pasada; the Oct-2024 suspension is visible in it).

`POST /hourly` takes `{MetricId, StartDate, EndDate, Entity, Filter}` and is
limited to 31 days per request, so longer ranges are split into chunks.
Hourly values arrive as strings in kWh; an empty string means no flow that
hour and is counted as zero in the daily/monthly totals (`horas_con_flujo`
reports how many hours had a value). Every day or month in the range is
reported, with 0 GWh when no hour had flow, so a suspension shows as zeros
rather than as missing periods. Metrics are Colombian exports
(`ExpoEner`, Colombia -> Ecuador) and imports (`ImpoEner`, Ecuador ->
Colombia), by `Enlace`; Ecuador links are those whose code contains
"ECUADOR".
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import post_json_bytes
from helpers.logging import MAIN_LOGGER_NAME

logger = logging.getLogger(MAIN_LOGGER_NAME)

_URL = "https://servapibi.xm.com.co/hourly"
_MAX_DAYS_PER_REQUEST = 31
_MAX_RANGE_DAYS = 366
_METRICAS = {"exportaciones": "ExpoEner", "importaciones": "ImpoEner"}
_SENTIDO = {
    "exportaciones": "Colombia → Ecuador",
    "importaciones": "Ecuador → Colombia",
}

# Past days never change; the last few days can still be revised.
_chunk_cache = TtlCache(ttl_seconds=3600.0, max_entries=128)
_sem = asyncio.Semaphore(3)


def _chunks(desde: date, hasta: date) -> list[tuple[date, date]]:
    out = []
    start = desde
    while start <= hasta:
        end = min(start + timedelta(days=_MAX_DAYS_PER_REQUEST - 1), hasta)
        out.append((start, end))
        start = end + timedelta(days=1)
    return out


async def _fetch_chunk(metric: str, start: date, end: date) -> list[dict[str, Any]]:
    key = f"{metric}:{start}:{end}"
    cached = _chunk_cache.get(key)
    if cached is not None:
        return cached
    body = {
        "MetricId": metric,
        "StartDate": start.isoformat(),
        "EndDate": end.isoformat(),
        "Entity": "Enlace",
        "Filter": [],
    }
    async with _sem:
        logger.info("XM POST %s %s..%s", metric, start, end)
        content, truncated = await post_json_bytes(_URL, body)
    if truncated:
        raise ValueError(f"La respuesta de XM para {start}..{end} superó el límite de descarga.")
    data = json.loads(content)
    items = data.get("Items") or []
    _chunk_cache.set(key, items)
    return items


def _to_kwh(raw: Any) -> float | None:
    # Blank strings and nulls both mean no value for that hour.
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _periods(desde: date, hasta: date, agregacion: str) -> list[str]:
    days = [desde + timedelta(days=n) for n in range((hasta - desde).days + 1)]
    labels = [d.isoformat() if agregacion == "dia" else d.isoformat()[:7] for d in days]
    return list(dict.fromkeys(labels))


async def get_intercambio(
    desde: str,
    hasta: str,
    sentido: str = "exportaciones",
    agregacion: str = "dia",
) -> dict[str, Any]:
    """
    Energy exchanged between Colombia and Ecuador, aggregated from hourly data.

    Args:
        desde / hasta: ISO dates (YYYY-MM-DD), inclusive, at most 366 days.
        sentido: "exportaciones" (Colombia -> Ecuador) or "importaciones"
            (Ecuador -> Colombia).
        agregacion: "dia" or "mes".
    """
    if sentido not in _METRICAS:
        raise ValueError("`sentido` debe ser exportaciones o importaciones.")
    if agregacion not in {"dia", "mes"}:
        raise ValueError("`agregacion` debe ser dia o mes.")
    try:
        d0, d1 = date.fromisoformat(desde), date.fromisoformat(hasta)
    except ValueError as e:
        raise ValueError("Las fechas deben tener formato YYYY-MM-DD.") from e
    if d0 > d1:
        raise ValueError("`desde` no puede ser posterior a `hasta`.")
    if (d1 - d0).days + 1 > _MAX_RANGE_DAYS:
        raise ValueError(f"El rango máximo es de {_MAX_RANGE_DAYS} días; acota las fechas.")
    if d0 < date(2003, 1, 1):
        raise ValueError("XM tiene datos desde 2003.")

    metric = _METRICAS[sentido]
    chunk_items = await asyncio.gather(*(_fetch_chunk(metric, s, e) for s, e in _chunks(d0, d1)))

    kwh: dict[tuple[str, str], float] = defaultdict(float)
    hours: dict[tuple[str, str], int] = defaultdict(int)
    for items in chunk_items:
        for item in items:
            day = item["Date"][:10]
            period = day if agregacion == "dia" else day[:7]
            for ent in item.get("HourlyEntities") or []:
                values = ent.get("Values") or {}
                enlace = values.get("code", "")
                if "ECUADOR" not in enlace.upper():
                    continue
                for k, raw in values.items():
                    if not k.startswith("Hour"):
                        continue
                    v = _to_kwh(raw)
                    if v is None:
                        continue
                    kwh[(period, enlace)] += v
                    hours[(period, enlace)] += 1

    # Fill every period x link with zero so days without flow stay visible.
    periodos = _periods(d0, d1, agregacion)
    enlaces = sorted({enlace for _, enlace in kwh})
    registros = [
        {
            "periodo": period,
            "enlace": enlace,
            "energia_gwh": round(kwh.get((period, enlace), 0.0) / 1_000_000, 6),
            "horas_con_flujo": hours.get((period, enlace), 0),
        }
        for period in periodos
        for enlace in enlaces
    ]
    por_periodo: dict[str, float] = dict.fromkeys(periodos, 0.0)
    for (period, _), total in kwh.items():
        por_periodo[period] += total / 1_000_000
    return {
        "sentido": _SENTIDO[sentido],
        "agregacion": agregacion,
        "desde": d0.isoformat(),
        "hasta": d1.isoformat(),
        "total_gwh": round(sum(por_periodo.values()), 6),
        "total_por_periodo": {p: round(v, 6) for p, v in sorted(por_periodo.items())},
        "total_registros": len(registros),
        "registros": registros,
        "source": "XM (Colombia) — servapibi.xm.com.co",
        "url_fuente": "https://www.xm.com.co/",
    }

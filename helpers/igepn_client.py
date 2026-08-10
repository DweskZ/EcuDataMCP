"""Client for the Instituto Geofísico EPN (IG-EPN) public earthquake feed.

The IG-EPN publishes its recent seismic catalog as a flat CSV at
https://www.igepn.edu.ec/portal/eventos/www/events.csv with columns
latitude,longitude,mag,depth,time,status,id,place. The `place` column is not
quoted, so any commas inside it spill into extra fields that must be re-joined.
Timestamps carry no timezone metadata; the portal renders them as Ecuador
continental local time (UTC-05:00).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unicodedata import category, normalize

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_TIMEOUT = 35.0
_EVENTS_CSV_URL = "https://www.igepn.edu.ec/portal/eventos/www/events.csv"
_EVENT_PAGE_TEMPLATE = (
    "https://www.igepn.edu.ec/portal/eventos/www/events/{event_id}/overview.html"
)
_ECUADOR_TZ = timezone(timedelta(hours=-5))
_DEFAULT_COLUMNS = ("latitude", "longitude", "mag", "depth", "time", "status", "id", "place")
_TIME_FORMATS = ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")

_events_cache = TtlCache(ttl_seconds=120.0, max_entries=4)


def _strip(text: str) -> str:
    nfkd = normalize("NFKD", text or "")
    return "".join(c for c in nfkd if category(c) != "Mn").lower()


async def _get_text(url: str) -> str:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv, text/plain, */*"},
        follow_redirects=True,
        timeout=_TIMEOUT,
    ) as session:
        logger.debug("IGEPN GET %s", url)
        resp = await session.get(url)
        resp.raise_for_status()
        return resp.text


def _parse_time(raw: str) -> tuple[str, str] | None:
    """Return (local ISO, UTC ISO) for a feed timestamp, or None if unparseable."""
    value = (raw or "").strip()
    for fmt in _TIME_FORMATS:
        try:
            local = datetime.strptime(value, fmt).replace(tzinfo=_ECUADOR_TZ)
        except ValueError:
            continue
        return local.isoformat(), local.astimezone(UTC).isoformat()
    return None


def parse_events_csv(text: str) -> list[dict[str, Any]]:
    """Parse the IG-EPN events.csv payload into normalized event dicts."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return []

    columns = _DEFAULT_COLUMNS
    first_fields = [f.strip().lower() for f in lines[0].split(",")]
    if "latitude" in first_fields and "id" in first_fields:
        columns = tuple(first_fields)
        lines = lines[1:]

    events: list[dict[str, Any]] = []
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < len(columns):
            continue
        # `place` (the last column) is unquoted and may itself contain commas.
        head = parts[: len(columns) - 1]
        tail = ", ".join(parts[len(columns) - 1 :])
        record = dict(zip(columns[:-1], head, strict=False))
        record[columns[-1]] = tail

        times = _parse_time(record.get("time", ""))
        try:
            event = {
                "id": record.get("id") or None,
                "magnitud": float(record["mag"]),
                "profundidad_km": round(float(record["depth"]), 1),
                "latitud": float(record["latitude"]),
                "longitud": float(record["longitude"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
        if not event["id"] or times is None:
            continue
        event["tiempo_local"] = times[0]
        event["tiempo_utc"] = times[1]
        event["estado"] = record.get("status", "")
        event["localizacion"] = " ".join(record.get("place", "").split())
        event["url"] = _EVENT_PAGE_TEMPLATE.format(event_id=event["id"])
        events.append(event)

    events.sort(key=lambda ev: ev["tiempo_utc"], reverse=True)
    return events


async def _fetch_events() -> list[dict[str, Any]]:
    cached = _events_cache.get("events")
    if cached is not None:
        return cached
    events = parse_events_csv(await _get_text(_EVENTS_CSV_URL))
    _events_cache.set("events", events)
    return events


async def list_earthquakes(
    query: str = "",
    min_magnitud: float = 0.0,
    dias: int = 0,
    limit: int = 15,
) -> dict[str, Any]:
    """
    Fetch recent earthquakes from the IG-EPN catalog and filter client-side.

    Args:
        query: Free text matched (accent-insensitive) against place/id/status.
        min_magnitud: Keep events with magnitude >= this value.
        dias: Keep events from the last N days (0 = no date filter).
        limit: Max events returned (1-100).
    """
    events = await _fetch_events()

    q = _strip(query)
    cutoff = (
        (datetime.now(UTC) - timedelta(days=dias)).isoformat() if dias > 0 else ""
    )

    matched = []
    for ev in events:
        if ev["magnitud"] < min_magnitud:
            continue
        if cutoff and ev["tiempo_utc"] < cutoff:
            continue
        if q:
            blob = _strip(f"{ev['localizacion']} {ev['id']} {ev['estado']}")
            if q not in blob:
                continue
        matched.append(ev)

    limit = min(max(limit, 1), 100)
    return {
        "total": len(matched),
        "source": "IG-EPN catálogo sísmico (events.csv)",
        "url_fuente": _EVENTS_CSV_URL,
        "nota_horaria": "tiempo_local es hora continental de Ecuador (UTC-05:00)",
        "events": matched[:limit],
    }

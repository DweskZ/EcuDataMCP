"""Client for the Instituto Geofísico EPN (IG-EPN) public earthquake feed.

The IG-EPN publishes machine-readable earthquake exports as flat CSV, but the
exact column names/order are not documented and have been observed to differ
across sources: the live map feed at
https://www.igepn.edu.ec/portal/eventos/www/events.csv is expected to use
`latitude,longitude,mag,depth,time,status,id,place` (unlabeled time, assumed
Ecuador local UTC-05:00), while an archived historical export uses
`Mag,Lat,Long,Prof,Region,Hora UTC,Update,ID` (explicitly UTC). Neither of
these could be verified against the live server from this codebase's CI
environment (network egress to igepn.edu.ec is blocked here), so the parser
below is header-driven: it recognizes common column name variants (accent/
case-insensitive) in whatever order they appear, and only falls back to the
`events.csv` column guess above when no header row is detected. If the real
feed uses yet another header spelling, add it to `_COLUMN_SYNONYMS` below.

A `place`-like column is not quoted in any known source, so a comma inside a
place name (e.g. "a 53 km de Macas, Morona Santiago") spills into extra CSV
fields; those are re-joined back into the place column.
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

# Canonical field -> known header spellings seen across IG-EPN exports (already
# accent/case-normalized via _strip). Extend if a real feed uses another name.
_COLUMN_SYNONYMS: dict[str, set[str]] = {
    "latitude": {"latitude", "lat"},
    "longitude": {"longitude", "long", "lon", "lng"},
    "mag": {"mag", "magnitude", "magnitud"},
    "depth": {"depth", "prof", "profundidad"},
    "time": {"time", "hora utc", "hora", "fecha", "fecha utc"},
    "status": {"status", "estado"},
    "id": {"id"},
    "place": {"place", "region", "lugar", "zona", "sector"},
}
_HEADER_MATCH_THRESHOLD = 4  # min recognized columns to trust a row as a header

_events_cache = TtlCache(ttl_seconds=120.0, max_entries=4)


def _strip(text: str) -> str:
    nfkd = normalize("NFKD", text or "")
    return "".join(c for c in nfkd if category(c) != "Mn").lower()


def _match_column(token: str) -> str | None:
    norm = _strip(token.strip())
    for canonical, names in _COLUMN_SYNONYMS.items():
        if norm in names:
            return canonical
    return None


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


def _parse_time(raw: str, already_utc: bool = False) -> tuple[str, str] | None:
    """Return (local ISO, UTC ISO) for a feed timestamp, or None if unparseable."""
    value = (raw or "").strip()
    for fmt in _TIME_FORMATS:
        try:
            naive = datetime.strptime(value, fmt)  # noqa: DTZ007 (tz applied below)
        except ValueError:
            continue
        if already_utc:
            utc = naive.replace(tzinfo=UTC)
            local = utc.astimezone(_ECUADOR_TZ)
        else:
            local = naive.replace(tzinfo=_ECUADOR_TZ)
            utc = local.astimezone(UTC)
        return local.isoformat(), utc.isoformat()
    return None


def _detect_columns(lines: list[str]) -> tuple[list[str | None], bool, list[str]]:
    """
    Inspect the first line: if enough fields match known column names, treat
    it as a header (returning the mapped columns, whether `time` is already
    UTC, and the remaining data lines). Otherwise assume the events.csv guess
    and treat all lines as data.
    """
    first_fields = [f.strip() for f in lines[0].split(",")]
    mapped = [_match_column(f) for f in first_fields]
    if sum(1 for m in mapped if m) >= _HEADER_MATCH_THRESHOLD:
        time_is_utc = False
        if "time" in mapped:
            time_is_utc = "utc" in first_fields[mapped.index("time")].lower()
        return mapped, time_is_utc, lines[1:]
    return list(_DEFAULT_COLUMNS), False, lines


def parse_events_csv(text: str) -> list[dict[str, Any]]:
    """Parse an IG-EPN earthquake CSV export into normalized event dicts."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return []

    columns, time_is_utc, lines = _detect_columns(lines)
    # A comma-containing place/region name spills into extra fields; merge
    # any overflow back into the place column (or the last column if no
    # place-like column was recognized).
    merge_idx = columns.index("place") if "place" in columns else len(columns) - 1

    events: list[dict[str, Any]] = []
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < len(columns):
            continue
        if len(parts) > len(columns):
            overflow = len(parts) - len(columns)
            merged = ", ".join(parts[merge_idx : merge_idx + 1 + overflow])
            parts = parts[:merge_idx] + [merged] + parts[merge_idx + 1 + overflow :]

        record: dict[str, str] = {}
        for col, val in zip(columns, parts, strict=True):
            if col:
                record[col] = val

        times = _parse_time(record.get("time", ""), already_utc=time_is_utc)
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
        "nota_horaria": (
            "tiempo_local/tiempo_utc se calculan según la columna de hora del "
            "feed: si su encabezado indica UTC se usa directo, si no se asume "
            "hora continental de Ecuador (UTC-05:00)"
        ),
        "events": matched[:limit],
    }

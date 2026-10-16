"""Ecuador mainland local time helpers.

Ecuador mainland is UTC-5 year-round (no DST), so a fixed offset is exact and
needs no tzdata. Use these wherever "today" or "the current year" is meant:
UTC would flip the date at 19:00 local time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

ECUADOR_TZ = timezone(timedelta(hours=-5))


def now_ecuador() -> datetime:
    return datetime.now(UTC).astimezone(ECUADOR_TZ)


def today_ecuador() -> date:
    return now_ecuador().date()

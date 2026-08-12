from datetime import UTC, datetime, timedelta

import pytest

from helpers import igepn_client
from helpers.cache import TtlCache

SAMPLE_CSV = (
    "latitude,longitude,mag,depth,time,status,id,place\n"
    "-2.1043,-77.6736,4.30,12.9727,2026/06/30 06:02:05,confirmed,igepn2026mrim,"
    "a 53.97 km de Macas, Morona Santiago\n"
    "-0.2500,-78.5200,3.10,8.0,2026/07/01 10:00:00,automatic,igepn2026zzzz,"
    "a 5 km de Quito, Pichincha\n"
)


def test_parse_events_csv_fields():
    events = igepn_client.parse_events_csv(SAMPLE_CSV)
    assert len(events) == 2
    # Sorted newest first
    assert events[0]["id"] == "igepn2026zzzz"
    ev = events[1]
    assert ev["id"] == "igepn2026mrim"
    assert ev["magnitud"] == 4.3
    assert ev["profundidad_km"] == 13.0
    assert ev["latitud"] == -2.1043
    assert ev["longitud"] == -77.6736
    # Unquoted commas in place are re-joined
    assert ev["localizacion"] == "a 53.97 km de Macas, Morona Santiago"
    # Local time (UTC-5) converted to UTC
    assert ev["tiempo_local"] == "2026-06-30T06:02:05-05:00"
    assert ev["tiempo_utc"] == "2026-06-30T11:02:05+00:00"
    assert ev["url"].endswith("/events/igepn2026mrim/overview.html")


def test_parse_events_csv_without_header_and_bad_rows():
    body = (
        "-2.1,-77.6,4.30,12.9,2026/06/30 06:02:05,confirmed,igepn2026mrim,Macas\n"
        "not,a,valid,row\n"
        "x,y,z,1,2026/06/30 06:02:05,confirmed,igepn2026bad,Quito\n"
    )
    events = igepn_client.parse_events_csv(body)
    assert [ev["id"] for ev in events] == ["igepn2026mrim"]


def test_parse_events_csv_alternate_schema_utc_header():
    # Real-world historical IG-EPN export uses a different column order/names
    # (Spanish + abbreviated) and explicitly labels the time column as UTC.
    body = (
        "Mag,Lat,Long,Prof,Region,Hora UTC,Update,ID\n"
        "3.7,0.35,-80.81,10,COSTA DE ECUADOR,2019-05-30 09:14:59,"
        "2019-05-30 09:31:32,igepn2019kmyh\n"
        "2.1,-0.19,-78.52,4,PICHINCHA,2019-05-29 01:13:43,"
        "2019-05-29 01:21:04,igepn2019kkmw\n"
    )
    events = igepn_client.parse_events_csv(body)
    assert len(events) == 2
    ev = next(e for e in events if e["id"] == "igepn2019kmyh")
    assert ev["magnitud"] == 3.7
    assert ev["latitud"] == 0.35
    assert ev["longitud"] == -80.81
    assert ev["profundidad_km"] == 10.0
    assert ev["localizacion"] == "COSTA DE ECUADOR"
    # "Hora UTC" header means the value is UTC already, not Ecuador local
    assert ev["tiempo_utc"] == "2019-05-30T09:14:59+00:00"
    assert ev["tiempo_local"] == "2019-05-30T04:14:59-05:00"
    # Unmapped "Update" column is simply ignored, not misread as status
    assert ev["estado"] == ""


async def test_list_earthquakes_filters(monkeypatch):
    async def fake_get_text(url: str) -> str:
        assert url.endswith("events.csv")
        return SAMPLE_CSV

    monkeypatch.setattr(igepn_client, "_get_text", fake_get_text)
    monkeypatch.setattr(igepn_client, "_events_cache", TtlCache(ttl_seconds=60))

    result = await igepn_client.list_earthquakes(min_magnitud=4.0)
    assert result["total"] == 1
    assert result["events"][0]["id"] == "igepn2026mrim"

    # Accent-insensitive text match on place
    result = await igepn_client.list_earthquakes(query="pichincha")
    assert result["total"] == 1
    assert result["events"][0]["localizacion"].endswith("Pichincha")

    result = await igepn_client.list_earthquakes(limit=1)
    assert result["total"] == 2
    assert len(result["events"]) == 1


async def test_list_earthquakes_days_filter(monkeypatch):
    recent = (datetime.now(UTC) - timedelta(days=1)).astimezone(
        igepn_client._ECUADOR_TZ
    )
    csv = (
        "latitude,longitude,mag,depth,time,status,id,place\n"
        f"-2.1,-77.6,4.0,10,{recent.strftime('%Y/%m/%d %H:%M:%S')},confirmed,igreciente,Macas\n"
        "-2.1,-77.6,4.0,10,2020/01/01 00:00:00,confirmed,igviejo,Macas\n"
    )

    async def fake_get_text(url: str) -> str:
        return csv

    monkeypatch.setattr(igepn_client, "_get_text", fake_get_text)
    monkeypatch.setattr(igepn_client, "_events_cache", TtlCache(ttl_seconds=60))

    result = await igepn_client.list_earthquakes(dias=7)
    assert [ev["id"] for ev in result["events"]] == ["igreciente"]


async def test_list_earthquakes_uses_cache(monkeypatch):
    calls = {"n": 0}

    async def fake_get_text(url: str) -> str:
        calls["n"] += 1
        return SAMPLE_CSV

    monkeypatch.setattr(igepn_client, "_get_text", fake_get_text)
    monkeypatch.setattr(igepn_client, "_events_cache", TtlCache(ttl_seconds=60))

    await igepn_client.list_earthquakes()
    await igepn_client.list_earthquakes(min_magnitud=4.0)
    assert calls["n"] == 1


@pytest.mark.parametrize(
    "raw,expected_utc",
    [
        ("2026/06/30 06:02:05", "2026-06-30T11:02:05+00:00"),
        ("2026-06-30 06:02:05", "2026-06-30T11:02:05+00:00"),
        ("2026-06-30T06:02:05", "2026-06-30T11:02:05+00:00"),
    ],
)
def test_parse_time_formats(raw, expected_utc):
    parsed = igepn_client._parse_time(raw)
    assert parsed is not None
    assert parsed[1] == expected_utc


def test_parse_time_invalid():
    assert igepn_client._parse_time("ayer") is None

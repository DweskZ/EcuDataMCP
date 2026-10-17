from datetime import UTC, datetime

from helpers import ecuador_time


def test_today_ecuador_lags_utc_after_19h_local(monkeypatch):
    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            # 2027-01-01 01:00 UTC is still 2026-12-31 20:00 in Ecuador.
            return datetime(2027, 1, 1, 1, 0, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(ecuador_time, "datetime", _FakeDatetime)

    assert ecuador_time.today_ecuador().isoformat() == "2026-12-31"

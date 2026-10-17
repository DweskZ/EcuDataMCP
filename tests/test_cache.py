import time

from helpers.cache import TtlCache


def test_ttl_cache_get_set():
    cache = TtlCache(ttl_seconds=60)
    assert cache.get("k") is None
    cache.set("k", {"ok": True})
    assert cache.get("k") == {"ok": True}


def test_ttl_cache_expires():
    cache = TtlCache(ttl_seconds=0.01)
    cache.set("k", 1)
    time.sleep(0.02)
    assert cache.get("k") is None


def test_ttl_cache_set_drops_expired_entries_before_live_ones():
    cache = TtlCache(ttl_seconds=60, max_entries=2)
    cache.set("fresh", 1)
    # Already expired: must be the one evicted, not the live "fresh" entry.
    cache._store["stale"] = (time.monotonic() - 1, 2)

    cache.set("new", 3)

    assert cache.get("fresh") == 1
    assert cache.get("new") == 3
    assert cache.get("stale") is None
    assert len(cache._store) == 2


def test_ttl_cache_set_drops_oldest_when_nothing_expired():
    cache = TtlCache(ttl_seconds=60, max_entries=2)
    cache.set("first", 1)
    cache.set("second", 2)

    cache.set("third", 3)

    assert cache.get("first") is None
    assert cache.get("second") == 2
    assert cache.get("third") == 3

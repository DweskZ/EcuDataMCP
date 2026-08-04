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

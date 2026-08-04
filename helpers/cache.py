"""Simple in-memory TTL cache for hot, rarely-changing API responses."""

from __future__ import annotations

import time
from collections.abc import Hashable
from typing import Any


class TtlCache:
    def __init__(self, ttl_seconds: float = 3600.0, max_entries: int = 256) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: dict[Hashable, tuple[float, Any]] = {}

    def get(self, key: Hashable) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: Hashable, value: Any) -> None:
        if len(self._store) >= self._max:
            # Drop expired first; if still full, drop an arbitrary oldest-ish entry.
            now = time.monotonic()
            expired = [k for k, (exp, _) in self._store.items() if now >= exp]
            for k in expired:
                self._store.pop(k, None)
            if len(self._store) >= self._max:
                self._store.pop(next(iter(self._store)))
        self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()


# Shared caches for catalog-style endpoints
categories_cache = TtlCache(ttl_seconds=3600.0)
instituciones_cache = TtlCache(ttl_seconds=1800.0)
sercop_search_cache = TtlCache(ttl_seconds=600.0, max_entries=128)

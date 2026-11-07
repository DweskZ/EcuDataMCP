"""TTL cache for hot, rarely-changing API responses, optionally kept on disk.

Most caches are in memory only. A cache built with ``persist="<name>"``
also writes its entries to ``<data_dir>/cache/<name>.json`` and reads them
back after a restart, so an expensive catalog (the BCE index pages, the SGR
library, the Superbancos sections) is not scraped again on every deploy.
Expiry is wall-clock time on disk, so a restart never extends an entry's
life. Set ``ECUADOR_MCP_DISK_CACHE=0`` to keep everything in memory.

Only values that survive a JSON round trip unchanged are written: a value
holding tuples, bytes or non-string dict keys would come back as a different
type, so it stays memory-only rather than being silently altered.

Expired entries are kept for ``stale_seconds`` more (7 days by default) so a
caller whose source is down can still answer from the last good copy:
``serve_stale(key, exc)`` returns it and records the fact, which the response
envelope reports as ``metadatos.frescura = "obsoleta"``. ``get`` never
returns an expired entry.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Hashable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from helpers.paths import data_dir
from helpers.response_contract import record_stale_response

logger = logging.getLogger("ecuador_mcp")


def disk_cache_enabled() -> bool:
    raw = os.getenv("ECUADOR_MCP_DISK_CACHE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _as_key(value: Any) -> Hashable:
    """JSON turns tuple keys into lists; turn them back."""
    if isinstance(value, list):
        return tuple(_as_key(v) for v in value)
    return value


def _round_trips(value: Any) -> bool:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False)) == value
    except (TypeError, ValueError):
        return False


def _key_round_trips(key: Hashable) -> bool:
    """Keys come back through _as_key, which restores tuples."""
    try:
        return _as_key(json.loads(json.dumps(key, ensure_ascii=False))) == key
    except (TypeError, ValueError):
        return False


class TtlCache:
    def __init__(
        self,
        ttl_seconds: float = 3600.0,
        max_entries: int = 256,
        persist: str | None = None,
        stale_seconds: float = 7 * 86400.0,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._persist = persist
        self._stale = stale_seconds
        self._loaded = False
        # key -> (wall-clock expiry, value)
        self._store: dict[Hashable, tuple[float, Any]] = {}

    def _path(self) -> Path | None:
        if not self._persist or not disk_cache_enabled():
            return None
        return data_dir() / "cache" / f"{self._persist}.json"

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self._path()
        if path is None or not path.is_file():
            return
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Disk cache %s unreadable, ignoring it: %s", path, exc)
            return
        now = time.time()
        for raw_key, (expires_at, value) in entries.items():
            if expires_at + self._stale > now:
                self._store.setdefault(_as_key(json.loads(raw_key)), (expires_at, value))

    def _save(self) -> None:
        path = self._path()
        if path is None:
            return
        entries = {
            json.dumps(key, ensure_ascii=False): [expires_at, value]
            for key, (expires_at, value) in self._store.items()
            if _key_round_trips(key) and _round_trips(value)
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            logger.warning("Could not write disk cache %s: %s", path, exc)

    def get(self, key: Hashable) -> Any | None:
        self._load()
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        now = time.time()
        if now >= expires_at:
            if now >= expires_at + self._stale:
                self._store.pop(key, None)
            return None
        return value

    def serve_stale(self, key: Hashable, exc: BaseException) -> Any | None:
        """Return the last good value for ``key`` after a failed refresh.

        Callers use it in the ``except`` around their fetch: a value still
        inside the stale window comes back and is recorded for the response
        envelope; ``None`` means there is nothing to fall back on, so the
        caller re-raises.
        """
        self._load()
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.time() >= expires_at + self._stale:
            return None
        stored_at = expires_at - self._ttl
        logger.warning(
            "Serving stale %s entry from %s after a failed refresh: %s",
            self._persist or "cache",
            datetime.fromtimestamp(stored_at, UTC).isoformat(),
            exc,
        )
        record_stale_response(self._persist or "cache", stored_at, exc)
        return value

    def set(self, key: Hashable, value: Any) -> None:
        self._load()
        if len(self._store) >= self._max:
            # Drop entries past their stale window, then expired ones; if
            # still full, drop an arbitrary oldest-ish entry.
            now = time.time()
            for cutoff in (self._stale, 0.0):
                gone = [k for k, (exp, _) in self._store.items() if now >= exp + cutoff]
                for k in gone:
                    self._store.pop(k, None)
                if len(self._store) < self._max:
                    break
            if len(self._store) >= self._max:
                self._store.pop(next(iter(self._store)))
        self._store[key] = (time.time() + self._ttl, value)
        if self._persist:
            self._save()

    def clear(self) -> None:
        self._store.clear()
        self._loaded = True
        path = self._path()
        if path is not None:
            path.unlink(missing_ok=True)


# Shared caches for catalog-style endpoints
categories_cache = TtlCache(ttl_seconds=3600.0)
sercop_search_cache = TtlCache(ttl_seconds=1800.0, max_entries=128)
